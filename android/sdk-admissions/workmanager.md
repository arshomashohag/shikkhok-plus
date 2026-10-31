# SDK admission: AndroidX WorkManager

- **Artifacts**: `androidx.work:work-runtime-ktx:2.9.1` (and its
  transitive `work-runtime`, Room 2.5.0, `lifecycle-service`,
  `startup-runtime`). `androidx.work:work-testing` is test-only.
- **What it is**: AndroidX WorkManager, published by Google, licensed
  Apache-2.0.
- **Why it is needed**: the app-icon count. A 15-minute periodic check
  reads the unread count from our own server and posts one tray
  notification. WorkManager is the platform-recommended scheduler and
  survives process death and reboot; the alternative is a foreground
  service, which is heavier and visible.
- **Network**: none of its own. The only request is our own
  `GET /v1/me/notifications`, made by `ApiClient`.
- **Identifiers**: sends no device or advertising identifier. It stores
  its job table in a local Room database on the device and transmits
  nothing.
- **Analytics and crash reporting**: none.
- **Forbidden-identifier check**: done against the project set (AAID,
  SIM serial, build serial, BSSID, MAC, SSID, IMEI, IMSI, AD_ID,
  TelephonyManager, SMS read, location). None is referenced by the
  dependency, and `verifyReleasePermissions` confirms no forbidden
  permission is merged.

## Permissions merged into the manifest

| Permission | Source | Purpose |
|---|---|---|
| `ACCESS_NETWORK_STATE` | WorkManager | Checks the network is up before running the check |
| `WAKE_LOCK` | WorkManager | Keeps the CPU awake while one check runs |
| `RECEIVE_BOOT_COMPLETED` | WorkManager | Re-registers the periodic check after a restart |
| `FOREGROUND_SERVICE` | WorkManager | Declared for expedited work; this app schedules none |
| `POST_NOTIFICATIONS` | This app | The unread tray notification (API 33+, asked once) |

The notification text carries only a count, never a name, batch or
amount.
