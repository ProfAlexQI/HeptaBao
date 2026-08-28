fn main() {
    let provider = rustls::crypto::aws_lc_rs::default_provider();
    let _ = provider;
}

#[cfg(test)]
mod tests {
    #[test]
    fn aws_lc_provider_is_constructible() {
        let provider = rustls::crypto::aws_lc_rs::default_provider();
        let _ = provider;
    }
}
