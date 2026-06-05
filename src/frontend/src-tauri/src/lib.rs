use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Manager, State};

struct BackendState {
    port: Mutex<Option<u16>>,
    process: Mutex<Option<Child>>,
}

#[tauri::command]
fn get_backend_port(state: State<BackendState>) -> Option<u16> {
    *state.port.lock().unwrap()
}

/// Walks up from the exe location looking for `src/backend/memo` package directory.
/// Works on any developer machine regardless of absolute path.
fn find_backend_dir() -> Option<std::path::PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let mut dir = exe.parent()?.to_path_buf();
    for _ in 0..12 {
        let candidate = dir.join("src").join("backend");
        if candidate.join("memo").exists() {
            return Some(candidate);
        }
        dir = dir.parent()?.to_path_buf();
    }
    None
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(BackendState {
            port: Mutex::new(None),
            process: Mutex::new(None),
        })
        .setup(|app| {
            let handle = app.handle().clone();

            #[cfg(debug_assertions)]
            let backend_dir_opt = find_backend_dir();

            #[cfg(not(debug_assertions))]
            let backend_dir_opt = app
                .path()
                .resource_dir()
                .ok()
                .map(|d| d.join("backend"));

            let Some(backend_dir) = backend_dir_opt else {
                eprintln!("[memo] Backend directory not found — skipping spawn");
                return Ok(());
            };

            let python: std::ffi::OsString = {
                #[cfg(target_os = "windows")]
                {
                    let venv = backend_dir.join(".venv").join("Scripts").join("python.exe");
                    if venv.exists() { venv.into() } else { "python".into() }
                }
                #[cfg(not(target_os = "windows"))]
                {
                    let venv = backend_dir.join(".venv").join("bin").join("python3");
                    if venv.exists() { venv.into() } else { "python3".into() }
                }
            };

            match Command::new(&python)
                .args(["-m", "memo.main"])
                .current_dir(&backend_dir)
                .stdout(Stdio::piped())
                .stderr(Stdio::inherit())
                .spawn()
            {
                Ok(mut child) => {
                    let stdout = child.stdout.take().expect("stdout is piped");
                    let reader = BufReader::new(stdout);
                    {
                        let state = handle.state::<BackendState>();
                        *state.process.lock().unwrap() = Some(child);
                    }
                    std::thread::spawn(move || {
                        for line in reader.lines().flatten() {
                            if let Some(port_str) = line.strip_prefix("MEMO_PORT=") {
                                if let Ok(port) = port_str.trim().parse::<u16>() {
                                    let state = handle.state::<BackendState>();
                                    *state.port.lock().unwrap() = Some(port);
                                }
                            }
                        }
                    });
                }
                Err(e) => eprintln!("[memo] Failed to spawn Python backend: {e}"),
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::Destroyed) {
                let state = window.app_handle().state::<BackendState>();
                let mut guard = state.process.lock().unwrap();
                if let Some(mut child) = guard.take() {
                    let _ = child.kill();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![get_backend_port])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
