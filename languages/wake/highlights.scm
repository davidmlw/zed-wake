(comment) @comment

[(integer) (double)] @number
(single_string) @string
(double_string) @string
(regexp) @string.regex
(interpolation) @embedded

[(low_identifier_expression) (low_identifier_pattern)] @variable
[(high_identifier_expression) (high_identifier_pattern)] @constructor
[(low_identifier_type) (high_identifier_type)] @type
(identifier_package) @string.special.symbol

[
  "binary" "data" "def" "else" "export" "from" "global" "here"
  "if" "import" "match" "package" "prim" "publish" "require"
  "subscribe" "target" "then" "topic" "tuple" "type" "unary"
] @keyword

["(" ")"] @punctuation.bracket
["=" ":" "\\" "->"] @punctuation.delimiter
[
  (dot_op) (composition_op) (unary_fn_op) (exponent_op) (muldiv_op)
  (addsub_op) (comparison_op) (inequality_op) (and_op) (or_op)
  (currency_op) (lr_arrow_op) (bi_arrow_op) (quantifier_op) (colon_op)
] @operator
(comma_op) @punctuation.delimiter

(application_expression fn: (low_identifier_expression) @function)
(low_application_pattern fn: (low_identifier_pattern) @function)
(definition pattern: (binary_pattern operator: (_) @function))
(definition pattern: (unary_pattern operator: (_) @function))
(field name: (high_identifier_pattern) @property)

((high_identifier_expression) @boolean
  (#any-of? @boolean "True" "False"))
