use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs,
    io::{self, IsTerminal, Write},
    path::{Path, PathBuf},
};
use wraith_core::{
    config,
    error::{self, Error},
};

pub const PYTHON: &str = include_str!("../../../adapters/python/wraith_adapter.py");
pub const NODE: &str = include_str!("../../../adapters/typescript/wraith-adapter.mjs");
const NODE_TYPES: &str = include_str!("../../../adapters/typescript/wraith-adapter.d.mts");

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
pub struct Project {
    pub version: u32,
    pub language: String,
    pub entrypoint: String,
    pub mode: String,
    pub model: Option<String>,
    #[serde(default)]
    pub required_env: Vec<String>,
}

pub fn directory(path: &Path) -> &Path {
    path.parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."))
}

pub fn load(directory: &Path) -> Result<Option<Project>, Error> {
    let path = directory.join("wraith.project.json");
    if !path.exists() {
        return Ok(None);
    }
    let project: Project =
        serde_json::from_slice(&fs::read(&path).map_err(|e| error::io("read project", &path, e))?)
            .map_err(|e| Error::Config(format!("{}: {e}", path.display())))?;
    if project.version != 1
        || !["python", "typescript", "protocol"].contains(&project.language.as_str())
        || !["offline", "live"].contains(&project.mode.as_str())
    {
        return Err(Error::Config(
            "wraith.project.json: unsupported version, language, or mode".into(),
        ));
    }
    if project
        .required_env
        .iter()
        .any(|n| n.is_empty() || !n.chars().all(|c| c.is_ascii_alphanumeric() || c == '_'))
    {
        return Err(Error::Config(
            "requiredEnv must contain environment variable names, never values".into(),
        ));
    }
    Ok(Some(project))
}

pub fn write_new(path: &Path, contents: &[u8]) -> Result<(), Error> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| error::io("create directory", parent, e))?;
    }
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| error::io("create file", path, e))?;
    file.write_all(contents)
        .map_err(|e| error::io("write file", path, e))
}

pub fn quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\\''"))
}

pub fn prompt(label: &str, default: &str) -> Result<String, Error> {
    print!("{label} [{default}]: ");
    io::stdout()
        .flush()
        .map_err(|e| error::io("flush prompt", Path::new("stdout"), e))?;
    let mut line = String::new();
    io::stdin()
        .read_line(&mut line)
        .map_err(|e| error::io("read prompt", Path::new("stdin"), e))?;
    Ok(if line.trim().is_empty() {
        default.into()
    } else {
        line.trim().into()
    })
}

pub struct InitOptions {
    pub entrypoint: Option<String>,
    pub language: Option<String>,
    pub runtime: Option<String>,
    pub mode: String,
    pub model: Option<String>,
    pub required_env: Vec<String>,
    pub template: String,
    pub demo: bool,
}

pub fn init(path: &Path, mut options: InitOptions) -> Result<(), Error> {
    let directory = directory(path);
    if path.exists() {
        return Err(Error::Config(format!(
            "{} already exists. Init never overwrites files; choose a new --config path.",
            path.display()
        )));
    }
    let detected = if directory.join("package.json").exists() {
        "typescript"
    } else {
        "python"
    };
    if options.entrypoint.is_none() && !options.demo && io::stdin().is_terminal() {
        println!(
            "Connect a function that accepts (input, context) and returns JSON.\nEnter demo to try Wraith without connecting an agent."
        );
        let value = prompt("Agent entrypoint", "demo")?;
        if value != "demo" {
            options.entrypoint = Some(value);
        }
    }
    if let Some(entrypoint) = options.entrypoint {
        let (target, name) = entrypoint
            .rsplit_once(':')
            .filter(|(a, b)| !a.is_empty() && !b.is_empty())
            .ok_or_else(|| {
                Error::Config("Use --entrypoint module:function or file.ts:export".into())
            })?;
        if !name.chars().all(|c| c.is_alphanumeric() || c == '_') {
            return Err(Error::Config(
                "Entrypoint export must be a function name".into(),
            ));
        }
        let language = options.language.unwrap_or_else(|| {
            if target.ends_with(".py") {
                "python".into()
            } else if [".ts", ".js", ".mjs", ".cjs"]
                .iter()
                .any(|ext| target.ends_with(ext))
            {
                "typescript".into()
            } else {
                detected.into()
            }
        });
        let runtime = options.runtime.unwrap_or_else(|| {
            if language == "typescript" {
                "node".into()
            } else {
                if cfg!(windows) { "python" } else { "python3" }.into()
            }
        });
        let (adapter_name, adapter) = if language == "python" {
            ("wraith_adapter.py", PYTHON)
        } else {
            ("wraith-adapter.mjs", NODE)
        };
        let project = Project {
            version: 1,
            language,
            entrypoint: entrypoint.clone(),
            mode: options.mode,
            model: options.model,
            required_env: options.required_env,
        };
        if !["python", "typescript"].contains(&project.language.as_str())
            || !["offline", "live"].contains(&project.mode.as_str())
        {
            return Err(Error::Config(
                "Choose python/typescript and offline/live".into(),
            ));
        }
        let adapter_path = directory.join(adapter_name);
        let project_path = directory.join("wraith.project.json");
        let types_path = directory.join("wraith-adapter.d.mts");
        for p in [&adapter_path, &project_path, &types_path] {
            if p.exists() {
                return Err(Error::Config(format!(
                    "{} already exists; no files overwritten",
                    p.display()
                )));
            }
        }
        let expect = match options.template.as_str() {
            "tools" => json!({"tools_called":["lookup"]}),
            "rag" => json!({"sources":{"include":["knowledge_base"]}}),
            _ => json!({"json":[{"path":"","check":{"op":"exists"}}]}),
        };
        let config = json!({"version":1,"agent":{"command":format!("{} {} {}",quote(&runtime),quote(adapter_name),quote(&entrypoint)),"timeout_ms":60000},"tests":[{"id":"first-case","input":{"text":"Replace this with a representative request"},"expect":expect}]});
        // Validate the generated configuration before writing any files.
        config::parse(&config.to_string())?;
        write_new(&adapter_path, adapter.as_bytes())?;
        if project.language == "typescript" {
            write_new(&types_path, NODE_TYPES.as_bytes())?;
        }
        write_new(
            &project_path,
            &serde_json::to_vec_pretty(&project).map_err(|e| Error::Config(e.to_string()))?,
        )?;
        write_new(
            path,
            &serde_json::to_vec_pretty(&config).map_err(|e| Error::Config(e.to_string()))?,
        )?;
        println!(
            "Connected {entrypoint}. Edit tests in {} to describe correct behavior.\nStarter checks need review; they do not establish answer quality.\nNext: wraith doctor, then wraith baseline{}",
            path.display(),
            if project.mode == "live" {
                " --allow-live --max-requests 20"
            } else {
                ""
            }
        );
    } else {
        let agent_path = directory.join("wraith_agent.py");
        if agent_path.exists() {
            return Err(Error::Config(format!(
                "{} already exists; no files overwritten",
                agent_path.display()
            )));
        }
        let contents = include_str!("../../../wraith.yaml")
            .replace("examples/python-agent/agent.py", "wraith_agent.py");
        let contents = if cfg!(windows) {
            contents.replacen("python3 ", "python ", 1)
        } else {
            contents
        };
        write_new(
            &agent_path,
            include_str!("../../../examples/python-agent/agent.py").as_bytes(),
        )?;
        write_new(path, contents.as_bytes())?;
        println!(
            "Created {} and {}.\nNext: wraith doctor, then wraith baseline\nTo connect your agent: wraith init --entrypoint file.py:function in a new config directory.",
            path.display(),
            agent_path.display()
        );
    }
    let ignore = directory.join(".gitignore");
    let existing = fs::read_to_string(&ignore).unwrap_or_default();
    if !existing
        .lines()
        .any(|l| l == ".wraith/" || l == "**/.wraith/")
    {
        let mut file = fs::OpenOptions::new()
            .append(true)
            .create(true)
            .open(&ignore)
            .map_err(|e| error::io("open gitignore", &ignore, e))?;
        file.write_all(b"\n.wraith/\n")
            .map_err(|e| error::io("write gitignore", &ignore, e))?;
    }
    Ok(())
}

pub fn executable(name: &str, directory: &Path) -> Option<PathBuf> {
    if name.contains('/') || name.contains('\\') {
        let p = directory.join(name);
        return p.is_file().then_some(p);
    }
    std::env::var_os("PATH")
        .into_iter()
        .flat_map(|paths| std::env::split_paths(&paths).collect::<Vec<_>>())
        .flat_map(|p| {
            if cfg!(windows) {
                vec![
                    p.join(name),
                    p.join(format!("{name}.exe")),
                    p.join(format!("{name}.cmd")),
                ]
            } else {
                vec![p.join(name)]
            }
        })
        .find(|p| p.is_file())
}

pub fn doctor(path: &Path) -> Result<(Value, bool), Error> {
    let (cfg, directory) = config::load(path)?;
    let project = load(&directory)?;
    let args = config::command_args(&cfg.agent.command)?;
    let mut checks = vec![
        json!({"status":"pass","message":format!("Valid configuration: {} scenarios",cfg.tests.len())}),
    ];
    let found = executable(&args[0], &directory).is_some();
    checks.push(json!({"status":if found{"pass"}else{"error"},"message":if found{format!("Executable available: {}",args[0])}else{format!("Install {} or update agent.command to its absolute path",args[0])}}));
    for argument in args
        .iter()
        .skip(1)
        .filter(|s| s.ends_with(".py") || s.ends_with(".mjs") || s.ends_with(".js"))
    {
        let present = directory.join(argument).is_file();
        checks.push(json!({"status":if present{"pass"}else{"error"},"message":format!("Agent script {} {}",argument,if present{"exists"}else{"is missing; correct the path relative to the config"})}));
    }
    if let Some(p) = project {
        let target = p
            .entrypoint
            .rsplit_once(':')
            .map(|(target, _)| target)
            .unwrap_or("");
        if target.ends_with(".py") || p.language == "typescript" {
            let present = directory.join(target).is_file();
            checks.push(json!({"status":if present{"pass"}else{"error"},"message":format!("Entrypoint {target} {}",if present{"exists"}else{"is missing; create the function wrapper or fix its path"})}));
        }
        for name in p.required_env {
            let present = std::env::var_os(&name).is_some_and(|v| !v.is_empty());
            checks.push(json!({"status":if present{"pass"}else{"error"},"message":format!("{name} {}",if present{"is set (value hidden)"}else{"is missing; export it or load your .env before running Wraith"})}));
        }
        checks.push(json!({"status":"info","message":format!("Mode: {}. Model label: {}. Live requests require SDK budget helpers, including retries.",p.mode,p.model.unwrap_or_else(||"not declared".into()))}));
    }
    let minimal = cfg.tests.iter().all(|s| {
        serde_json::to_value(&s.expect)
            .ok()
            .is_some_and(|v| v["json"].as_array().is_none_or(|a| a.len() <= 1))
            && s.expect.tools_called.is_empty()
            && s.expect.sources.include.is_empty()
            && s.expect.output_contains.is_empty()
    });
    if minimal {
        checks.push(json!({"status":"warning","message":"Review starter expectations: add allowed IDs, required tools/sources, or output constraints before relying on this gate"}));
    }
    checks.push(json!({"status":"info","message":"Doctor does not import or execute your agent. Run baseline to validate runtime dependencies and the function signature."}));
    let passed = !checks.iter().any(|c| c["status"] == "error");
    Ok((json!({"passed":passed,"checks":checks}), passed))
}
