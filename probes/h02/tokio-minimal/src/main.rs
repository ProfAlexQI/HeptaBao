use tokio::sync::oneshot;

#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() {
    let (sender, receiver) = oneshot::channel::<()>();
    let task = tokio::spawn(async move { receiver.await.is_err() });
    drop(sender);
    match task.await {
        Ok(true) => {}
        Ok(false) => panic!("cancelled oneshot unexpectedly produced a value"),
        Err(error) => panic!("probe task failed: {error}"),
    }
}

#[cfg(test)]
mod tests {
    use tokio::sync::oneshot;

    #[tokio::test(flavor = "current_thread")]
    async fn cancellation_wakes_waiter() {
        let (sender, receiver) = oneshot::channel::<()>();
        drop(sender);
        assert!(receiver.await.is_err());
    }

    #[tokio::test(flavor = "current_thread")]
    async fn timer_completes_under_real_time_profile() {
        tokio::time::sleep(std::time::Duration::from_millis(1)).await;
    }
}
