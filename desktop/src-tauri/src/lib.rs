use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::Duration;

use tauri::Manager;

struct BackendProcess(Mutex<Option<Child>>);

const BACKEND_ADDR: &str = "127.0.0.1:8000";

fn backend_already_running() -> bool {
    let addr = BACKEND_ADDR.parse().expect("valid socket address");
    TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok()
}

/// Repo root relative to this crate (desktop/src-tauri -> repo root).
/// Dev-tool assumption: the app runs from a checkout of the repository.
fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("repo root exists")
        .to_path_buf()
}

fn spawn_backend() -> Option<Child> {
    let mut cmd = Command::new("uv");
    cmd.args([
        "run",
        "uvicorn",
        "src.frontend.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ])
    .current_dir(repo_root());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    match cmd.spawn() {
        Ok(child) => Some(child),
        Err(err) => {
            eprintln!("failed to spawn backend: {err}");
            None
        }
    }
}

fn kill_backend(child: &mut Child) {
    // `uv run` wraps the real python process, so kill the whole tree;
    // a plain child.kill() would orphan uvicorn on Windows.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let _ = Command::new("taskkill")
            .args(["/T", "/F", "/PID", &child.id().to_string()])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }
    #[cfg(not(windows))]
    {
        let _ = child.kill();
    }
    let _ = child.wait();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let child = if backend_already_running() {
                None
            } else {
                spawn_backend()
            };
            app.manage(BackendProcess(Mutex::new(child)));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                let child = app_handle
                    .state::<BackendProcess>()
                    .0
                    .lock()
                    .ok()
                    .and_then(|mut guard| guard.take());
                if let Some(mut child) = child {
                    kill_backend(&mut child);
                }
            }
        });
}
