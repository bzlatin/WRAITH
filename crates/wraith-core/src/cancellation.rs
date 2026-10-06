use tokio::sync::watch;

/// One-way cancellation shared between the CLI and execution engine.
#[derive(Debug, Clone)]
pub struct Cancellation {
    sender: watch::Sender<bool>,
}

impl Default for Cancellation {
    fn default() -> Self {
        Self {
            sender: watch::channel(false).0,
        }
    }
}

impl Cancellation {
    pub fn cancel(&self) {
        self.sender.send_replace(true);
    }
    pub fn is_cancelled(&self) -> bool {
        *self.sender.borrow()
    }
    pub async fn cancelled(&self) {
        let mut receiver = self.sender.subscribe();
        loop {
            if *receiver.borrow_and_update() {
                return;
            }
            if receiver.changed().await.is_err() {
                return;
            }
        }
    }
}
