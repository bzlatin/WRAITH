use std::{io, process::ExitStatus};
use tokio::process::{ChildStderr, ChildStdin, ChildStdout, Command};

/// Platform containment is kept behind safe APIs; execution/evaluation stay portable.
pub(crate) struct Process {
    #[cfg(not(windows))]
    child: tokio::process::Child,
    #[cfg(windows)]
    child: Box<dyn process_wrap::tokio::ChildWrapper>,
    #[cfg(unix)]
    group_id: Option<u32>,
}

impl Process {
    pub fn spawn(command: Command) -> io::Result<Self> {
        #[cfg(not(windows))]
        {
            let mut command = command;
            command.kill_on_drop(true);
            #[cfg(unix)]
            command.process_group(0);
            let child = command.spawn()?;
            Ok(Self {
                #[cfg(unix)]
                group_id: child.id(),
                child,
            })
        }
        #[cfg(windows)]
        {
            use process_wrap::tokio::{CommandWrap, JobObject, KillOnDrop};
            let mut wrapped = CommandWrap::from(command);
            // JobObject suspends creation, assigns the job, then resumes the process.
            wrapped.wrap(KillOnDrop).wrap(JobObject);
            Ok(Self {
                child: wrapped.spawn()?,
            })
        }
    }

    pub fn take_pipes(&mut self) -> io::Result<(ChildStdin, ChildStdout, ChildStderr)> {
        #[cfg(not(windows))]
        let (stdin, stdout, stderr) = (
            &mut self.child.stdin,
            &mut self.child.stdout,
            &mut self.child.stderr,
        );
        #[cfg(windows)]
        let (stdin, stdout, stderr) = (
            self.child.stdin().take(),
            self.child.stdout().take(),
            self.child.stderr().take(),
        );
        #[cfg(windows)]
        let (mut stdin, mut stdout, mut stderr) = (stdin, stdout, stderr);
        Ok((
            stdin
                .take()
                .ok_or_else(|| io::Error::other("Agent stdin unavailable"))?,
            stdout
                .take()
                .ok_or_else(|| io::Error::other("Agent stdout unavailable"))?,
            stderr
                .take()
                .ok_or_else(|| io::Error::other("Agent stderr unavailable"))?,
        ))
    }

    pub async fn wait(&mut self) -> io::Result<ExitStatus> {
        #[cfg(not(windows))]
        {
            self.child.wait().await
        }
        #[cfg(windows)]
        {
            // Our sole child wrapper is JobObject. Wait for its inner direct child;
            // waiting for the whole job here could hold up a successful parent until
            // detached pipe-free descendants finish. Cleanup terminates the job next.
            self.child.inner_mut().wait().await
        }
    }

    pub fn terminate(&mut self) -> io::Result<()> {
        #[cfg(unix)]
        if let Some(id) = self.group_id.take().and_then(|id| i32::try_from(id).ok()) {
            use nix::{
                errno::Errno,
                sys::signal::{Signal, killpg},
                unistd::Pid,
            };
            match killpg(Pid::from_raw(id), Signal::SIGKILL) {
                Ok(()) | Err(Errno::ESRCH) => {}
                Err(error) => {
                    let _ = self.child.start_kill();
                    return Err(io::Error::from_raw_os_error(error as i32));
                }
            }
        }
        self.child.start_kill()
    }
}

impl Drop for Process {
    fn drop(&mut self) {
        let _ = self.terminate();
    }
}
