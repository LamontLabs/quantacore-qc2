# Owner identity offline recovery procedure

## Purpose and limits

Use this procedure when the owner has lost access to every enrolled device.
Recovery is not a routine sign-in and does not restore normal operating
authority. QC2-053 leaves promotion, entry, and reconciliation holds in place;
the replacement session is limited to `OWNER_READ` and `DEVICE_ADMIN`.
Do not clear those holds as part of identity recovery.

## Before recovery

- Use the offline recovery material issued during initial owner enrollment.
  It is returned once; keep it in an offline, access-controlled location.
- Generate a new P-256 signing key on the replacement device. The private key
  stays on that device and is never sent to the API, included in a recovery
  request, or written to application logs.
- Confirm the backend is using the intended environment namespace. Identity
  records and credentials are isolated by environment.
- Keep the replacement device's security level `UNKNOWN` unless the configured
  verifier has validated evidence for a stronger level. Android Keystore
  validation is handled by the later Android work.

## Recovery steps

1. Ask the identity service for a recovery challenge using the offline
   recovery material, replacement key ID, replacement public key, and app
   version.
2. Review the returned challenge and its expiration. The replacement device
   signs the canonical challenge bytes with its new P-256 private key using
   the recovery signing prefix.
3. Submit the challenge ID, recovery material, and replacement-key signature
   to complete recovery. Never include the offline material or signature in
   telemetry or diagnostic logs.
4. Treat recovery as complete only after the service returns the replacement
   session and the newly rotated offline recovery material. Store the new
   material offline and invalidate the prior copy.
5. Confirm through the identity status/read path that prior devices are
   revoked, the replacement device is enrolled, and promotion, entry, and
   reconciliation holds are all active. Confirm new entries remain paused.
6. Keep the replacement session restricted. Use the separate authorized
   recovery/reconciliation procedures to review state and release holds; this
   identity procedure does not grant that authority.

## Atomicity and failure handling

The database transition revokes prior device sessions, consumes the
single-use challenge, rotates recovery material, enrolls the replacement,
sets the holds, and appends recovery/pause evidence in one transaction. If
the evidence stream is unavailable or rejects a write, the transaction must
fail without partially completing recovery. Do not treat a failed request as
success or manually edit identity rows. Restore evidence-write availability,
check whether the challenge is still valid and unconsumed, then retry or issue
a new challenge as appropriate.

The backend stores only verifiers for recovery and session credentials. It
does not store the offline recovery material, device private keys, or broker
credentials.
