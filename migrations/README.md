# Migrations

Store schema changes here as ordered, immutable, forward-only migrations. Each
migration must state its purpose and compatibility expectations and receive
review before application. Do not edit an applied migration to repair history;
add a new corrective migration instead. Application startup must not apply
migrations automatically. Migration credentials remain offline from runtime
services, and destructive changes require a verified backup and explicit
approval.
