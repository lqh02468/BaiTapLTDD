class ApiConfig {
  static const String _configured = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://103.131.85.188:8080',
  );
  static String get baseUrl => _configured.replaceAll(RegExp(r'/$'), '');
}
