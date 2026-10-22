class ApiConfig {
  // Android phone over USB: run `adb reverse tcp:8080 tcp:8080`.
  // Android emulator without reverse: pass API_BASE_URL=http://10.0.2.2:8080.
  // Real phone over Wi-Fi: pass the laptop LAN IP using --dart-define.
  static const String _override = String.fromEnvironment('API_BASE_URL');
  static String get baseUrl => _override.isNotEmpty
      ? _override.replaceAll(RegExp(r'/$'), '')
      : 'http://127.0.0.1:8080';
}
