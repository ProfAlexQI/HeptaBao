fn main() {
    let provider = rustls::crypto::ring::default_provider();
    let _ = provider;
}

#[cfg(test)]
mod tests {
    #[test]
    fn ring_provider_is_constructible() {
        let provider = rustls::crypto::ring::default_provider();
        let _ = provider;
    }
}
