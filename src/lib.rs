use zed::settings::{CommandSettings, LspSettings};
use zed_extension_api::{self as zed, Command, LanguageServerId, Worktree};

struct WakeExtension;

fn launch_command(
    binary: Option<CommandSettings>,
    find_wake: impl FnOnce() -> Option<String>,
    mut env: zed::EnvVars,
) -> zed::Result<Command> {
    let binary = binary.unwrap_or(CommandSettings {
        path: None,
        arguments: None,
        env: None,
    });
    let command = match binary.path {
        Some(path) if path.trim().is_empty() => {
            return Err("lsp.wake.binary.path must not be empty".into());
        }
        Some(path) => path,
        None => find_wake().ok_or_else(|| {
            "Wake not found on the project host. Install Wake and add it to PATH, or set \
             lsp.wake.binary.path to its absolute path in Zed settings."
                .to_string()
        })?,
    };
    if let Some(overrides) = binary.env {
        env.retain(|(key, _)| !overrides.contains_key(key));
        env.extend(overrides);
    }
    Ok(Command {
        command,
        args: binary.arguments.unwrap_or_else(|| vec!["--lsp".into()]),
        env,
    })
}

impl zed::Extension for WakeExtension {
    fn new() -> Self {
        Self
    }

    fn language_server_command(
        &mut self,
        id: &LanguageServerId,
        worktree: &Worktree,
    ) -> zed::Result<Command> {
        let settings = LspSettings::for_worktree(id.as_ref(), worktree)?;
        launch_command(
            settings.binary,
            || worktree.which("wake"),
            worktree.shell_env(),
        )
    }

    fn language_server_initialization_options(
        &mut self,
        id: &LanguageServerId,
        worktree: &Worktree,
    ) -> zed::Result<Option<zed::serde_json::Value>> {
        Ok(LspSettings::for_worktree(id.as_ref(), worktree)?.initialization_options)
    }
}

zed::register_extension!(WakeExtension);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn discovers_wake_and_defaults_to_lsp() {
        let command = launch_command(None, || Some("/opt/wake/bin/wake".into()), vec![]).unwrap();
        assert_eq!(command.command, "/opt/wake/bin/wake");
        assert_eq!(command.args, ["--lsp"]);
    }

    #[test]
    fn explicit_path_skips_discovery_and_keeps_default_arguments() {
        let binary = CommandSettings {
            path: Some("/custom/wake".into()),
            arguments: None,
            env: None,
        };
        let command =
            launch_command(Some(binary), || panic!("must not search PATH"), vec![]).unwrap();
        assert_eq!(command.command, "/custom/wake");
        assert_eq!(command.args, ["--lsp"]);
    }

    #[test]
    fn respects_custom_arguments_and_environment() {
        let binary = CommandSettings {
            path: Some("/custom/wrapper".into()),
            arguments: Some(vec!["serve".into()]),
            env: Some([("PATH".into(), "/custom/bin".into())].into()),
        };
        let command = launch_command(
            Some(binary),
            || None,
            vec![
                ("PATH".into(), "/bin".into()),
                ("HOME".into(), "/home/test".into()),
            ],
        )
        .unwrap();
        assert_eq!(command.args, ["serve"]);
        assert!(command.env.contains(&("HOME".into(), "/home/test".into())));
        assert_eq!(
            command.env.iter().filter(|(key, _)| key == "PATH").count(),
            1
        );
        assert!(command.env.contains(&("PATH".into(), "/custom/bin".into())));
    }

    #[test]
    fn preserves_explicit_empty_arguments_for_direct_lsp_binary() {
        let binary = CommandSettings {
            path: Some("/opt/wake/lib/wake/lsp-wake".into()),
            arguments: Some(vec![]),
            env: None,
        };
        assert!(
            launch_command(Some(binary), || None, vec![])
                .unwrap()
                .args
                .is_empty()
        );
    }

    #[test]
    fn missing_wake_is_actionable() {
        let error = launch_command(None, || None, vec![]).unwrap_err();
        assert!(error.contains("project host"));
        assert!(error.contains("lsp.wake.binary.path"));
    }

    #[test]
    fn empty_explicit_path_is_not_silently_ignored() {
        let binary = CommandSettings {
            path: Some(" ".into()),
            arguments: None,
            env: None,
        };
        assert!(launch_command(Some(binary), || panic!("must not search PATH"), vec![]).is_err());
    }
}
