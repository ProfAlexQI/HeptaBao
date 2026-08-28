fn main() {
    let _ = std::mem::size_of::<openraft::Config>();
}

#[cfg(test)]
mod tests {
    #[test]
    fn config_type_is_available_without_candidate_types_crossing_domain_boundary() {
        assert!(std::mem::size_of::<openraft::Config>() > 0);
    }
}
