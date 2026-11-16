#include <string.h>
#include <stdlib.h>
#include <tree_sitter/parser.h>

#define MAX_HERE_PREFIX 8
#define MAX_STRING_DEPTH 24

_Static_assert(2 + 32 + MAX_STRING_DEPTH * (1 + MAX_HERE_PREFIX * sizeof(int32_t))
               <= TREE_SITTER_SERIALIZATION_BUFFER_SIZE, "scanner state must fit Tree-sitter's buffer");

enum TokenType {
  EOL,
  INDENT,
  DEDENT,
  COMMENT,
  STRING_START,
  STRING_MIDDLE,
  STRING_END,
  STRING_SIMPLE
};

struct StringContext {
  bool multiline;
  int32_t heredoc[MAX_HERE_PREFIX];
};

// Bound indentation and nested interpolation to the scanner serialization buffer.
struct Indentation {
  unsigned char depth;
  unsigned char stack[32];
  unsigned char string_depth;
  struct StringContext strings[MAX_STRING_DEPTH];
};

void *tree_sitter_wake_external_scanner_create() {
  struct Indentation *i = calloc(1, sizeof(struct Indentation));
  return i;
}

void tree_sitter_wake_external_scanner_destroy(void *payload) {
  free(payload);
}

unsigned tree_sitter_wake_external_scanner_serialize(void *payload, char *buffer) {
  struct Indentation *i = payload;
  unsigned length = 0;
  buffer[length++] = i->depth;
  memcpy(buffer + length, i->stack, i->depth);
  length += i->depth;
  buffer[length++] = i->string_depth;
  for (unsigned n = 0; n < i->string_depth; ++n) {
    buffer[length++] = i->strings[n].multiline;
    memcpy(buffer + length, i->strings[n].heredoc, sizeof(i->strings[n].heredoc));
    length += sizeof(i->strings[n].heredoc);
  }
  return length;
}

void tree_sitter_wake_external_scanner_deserialize(void *payload, const char *buffer, unsigned length) {
  struct Indentation *i = payload;
  memset(i, 0, sizeof(*i));
  if (length < 2) return;
  unsigned depth = (unsigned char)buffer[0];
  if (depth > sizeof(i->stack) || length < depth + 2) return;
  unsigned strings = (unsigned char)buffer[depth + 1];
  unsigned frame = 1 + sizeof(i->strings[0].heredoc);
  if (strings > MAX_STRING_DEPTH || length != depth + 2 + strings * frame) return;
  i->depth = depth;
  memcpy(i->stack, buffer + 1, depth);
  i->string_depth = strings;
  unsigned offset = depth + 2;
  for (unsigned n = 0; n < strings; ++n) {
    i->strings[n].multiline = buffer[offset++] != 0;
    memcpy(i->strings[n].heredoc, buffer + offset, sizeof(i->strings[n].heredoc));
    offset += sizeof(i->strings[n].heredoc);
  }
}

static bool is_lws(int32_t c) {
  return c == ' ' || c == '\t' || c == 0xa0 || c == 0x1680 ||
         (c >= 0x2000 && c <= 0x200a) ||
         c == 0x202f || c == 0x205f || c == 0x3000;
}
static bool is_nl(int32_t c) {
  return c == '\n' || c == '\v' || c == '\f' || c == '\r' ||
         c == 0x85 || c == 0x2028 || c == 0x2029;
}

static bool is_str_special(int32_t c) {
  return c == '"' || c == '\\' || c == '{';
}

static bool skip_till_close(TSLexer *lexer, const struct StringContext *context) {
  unsigned x = 0;
  unsigned p;
  int32_t ring[MAX_HERE_PREFIX], flat[MAX_HERE_PREFIX];

  // Measure the required escape string length
  for (p = 0; p < MAX_HERE_PREFIX; ++p)
    if (!context->heredoc[p]) break;

  // Clear ring
  memset(ring, 0, sizeof(ring));

top:
  while (!is_str_special(lexer->lookahead)) {
    if (lexer->eof(lexer)) return false;
    ring[x] = lexer->lookahead;
    if (++x == MAX_HERE_PREFIX) x = 0;
    lexer->advance(lexer, false);
  }

  // Re-align the last few charactersbefore the special character
  memcpy(&flat[0], &ring[x], (MAX_HERE_PREFIX-x)*sizeof(int32_t));
  memcpy(&flat[MAX_HERE_PREFIX-x], &ring[0], x*sizeof(int32_t));

  // If the prefix does not match, scan again.
  if (memcmp(context->heredoc, &flat[MAX_HERE_PREFIX-p], p*sizeof(int32_t)) != 0) {
    lexer->advance(lexer, false);
    goto top;
  }

  // If this was an escape, process it and continue
  if (lexer->lookahead == '\\') {
    lexer->advance(lexer, false);
    if (lexer->eof(lexer)) return false;
    lexer->advance(lexer, false);
    goto top;
  }
  return true;
}

enum StringStop { STOP_ERROR, STOP_END, STOP_INTERPOLATION };

// Modern multiline strings are raw except for %{...}; only a line-leading
// triple quote closes them, matching Wake's lex_mstr_continue.
static enum StringStop scan_multiline(TSLexer *lexer, bool line_start) {
  while (!lexer->eof(lexer)) {
    if (line_start) {
      while (is_lws(lexer->lookahead)) {
        lexer->advance(lexer, false);
      }
      if (lexer->lookahead == '"') {
        unsigned quotes = 0;
        while (quotes < 3 && lexer->lookahead == '"') {
          lexer->advance(lexer, false);
          ++quotes;
        }
        if (quotes == 3) {
          return STOP_END;
        }
        line_start = false;
        continue;
      }
    }
    if (lexer->lookahead == '%') {
      lexer->advance(lexer, false);
      if (lexer->lookahead == '{') {
        lexer->advance(lexer, false);
        return STOP_INTERPOLATION;
      }
      line_start = false;
      continue;
    }
    line_start = is_nl(lexer->lookahead);
    lexer->advance(lexer, false);
  }
  return STOP_ERROR;
}

static enum StringStop scan_string_tail(TSLexer *lexer, const struct StringContext *context,
                                       bool line_start) {
  if (context->multiline) return scan_multiline(lexer, line_start);
  if (!skip_till_close(lexer, context)) return STOP_ERROR;
  enum StringStop stop = lexer->lookahead == '"' ? STOP_END : STOP_INTERPOLATION;
  lexer->advance(lexer, false);
  return stop;
}

bool tree_sitter_wake_external_scanner_scan(void *payload, TSLexer *lexer, const bool *valid_symbols) {
  struct Indentation *i = payload;
  bool comment = false;

  // By default, consume nothing.
  // This is necessary to make it possible to produce INDENT/DEDENT out of nothing.
  lexer->mark_end(lexer);

  // Skip any trailing whitespace on the line
  while (is_lws(lexer->lookahead)) lexer->advance(lexer, false);

empty:
  if ((valid_symbols[STRING_START] || valid_symbols[STRING_SIMPLE]) && lexer->lookahead == '"') {
    struct StringContext context = {0};
    lexer->advance(lexer, false);
    if (lexer->lookahead == '"') {
      lexer->advance(lexer, false);
      if (lexer->lookahead == '"') {
        context.multiline = true;
        lexer->advance(lexer, false);
        while (is_lws(lexer->lookahead)) lexer->advance(lexer, false);
        if (!is_nl(lexer->lookahead)) return false;
        lexer->advance(lexer, false);
      } else {
        lexer->mark_end(lexer);
        lexer->result_symbol = STRING_SIMPLE;
        return valid_symbols[STRING_SIMPLE];
      }
    }
    if (!context.multiline) {
      for (int j = 0; j < MAX_HERE_PREFIX && !is_nl(lexer->lookahead) && !is_str_special(lexer->lookahead); ++j) {
        context.heredoc[j] = lexer->lookahead;
        lexer->advance(lexer, false);
      }
      if (!is_nl(lexer->lookahead)) memset(context.heredoc, 0, sizeof(context.heredoc));
    }
    enum StringStop stop = scan_string_tail(lexer, &context, context.multiline);
    if (stop == STOP_END) {
      lexer->mark_end(lexer);
      lexer->result_symbol = STRING_SIMPLE;
      return valid_symbols[STRING_SIMPLE];
    }
    if (stop == STOP_INTERPOLATION && valid_symbols[STRING_START] && i->string_depth < MAX_STRING_DEPTH) {
      i->strings[i->string_depth++] = context;
      lexer->mark_end(lexer);
      lexer->result_symbol = STRING_START;
      return valid_symbols[STRING_START];
    }
  }

  if ((valid_symbols[STRING_MIDDLE] || valid_symbols[STRING_END]) && lexer->lookahead == '}') {
    if (!i->string_depth) return false;
    const struct StringContext *context = &i->strings[i->string_depth - 1];
    if (context->multiline) lexer->advance(lexer, false);
    enum StringStop stop = scan_string_tail(lexer, context, false);
    if (stop == STOP_END && valid_symbols[STRING_END]) {
      --i->string_depth;
      lexer->mark_end(lexer);
      lexer->result_symbol = STRING_END;
      return valid_symbols[STRING_END];
    }
    if (stop == STOP_INTERPOLATION) {
      lexer->mark_end(lexer);
      lexer->result_symbol = STRING_MIDDLE;
      return valid_symbols[STRING_MIDDLE];
    }
  }

  // Skip over comment contents
  if (valid_symbols[COMMENT] && lexer->lookahead == '#') {
    comment = true;
    do lexer->advance(lexer, false);
    while (lexer->lookahead && !is_nl(lexer->lookahead));
    lexer->mark_end(lexer);
  }

  // If there is still stuff on the current line, there is no EOL/INDENT/DEDENT/COMMENT.
  if (!is_nl(lexer->lookahead)) return false;

  // Skip the leading whitespace
  do lexer->advance(lexer, false);
  while (is_lws(lexer->lookahead));

  // Allow empty lines
  if (is_nl(lexer->lookahead) || lexer->lookahead == '#') goto empty;

  if (comment) {
    lexer->result_symbol = COMMENT;
    return true;
  }

  // How deeply indented are we?
  unsigned newdepth = lexer->get_column(lexer);

  // How deeply indented WERE we?
  unsigned olddepth = i->depth ? i->stack[i->depth-1] : 0;

  if (valid_symbols[INDENT] && newdepth > olddepth && newdepth < 256) {
    if (i->depth < sizeof(i->stack)) {
      i->stack[i->depth] = newdepth;
      ++i->depth;
      lexer->result_symbol = INDENT;
      return true;
    } else {
      // forbid too many levels of nested scope
      return false;
    }
  }

  if (valid_symbols[DEDENT] && newdepth < olddepth) {
    --i->depth;
    lexer->result_symbol = DEDENT;
    return true;
  }

  if (valid_symbols[EOL] && newdepth == olddepth) {
    lexer->mark_end(lexer);
    lexer->result_symbol = EOL;
    return true;
  }

  return false;
}
