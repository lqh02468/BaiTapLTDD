import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'api_config.dart';

class ApiException implements Exception {
  final String message;
  final String? code;
  ApiException(this.message, {this.code});
  @override
  String toString() => message;
}

class Api {
  Api({String? baseUrl}) : _baseUrl = baseUrl ?? ApiConfig.baseUrl;

  final String _baseUrl;
  final HttpClient _client = HttpClient()
    ..connectionTimeout = const Duration(seconds: 5);
  String? token;

  Future<Map<String, dynamic>> request(String method, String path,
      [Map<String, dynamic>? data]) async {
    try {
      final uri = Uri.parse('$_baseUrl$path');
      final request = await _client.openUrl(method, uri).timeout(
            const Duration(seconds: 8),
          );
      request.headers.contentType = ContentType.json;
      if (token != null) {
        request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
      }
      if (data != null) {
        final payload = utf8.encode(jsonEncode(data));
        request.contentLength = payload.length;
        request.add(payload);
      }
      final response =
          await request.close().timeout(const Duration(seconds: 8));
      final rawBody = await utf8.decoder.bind(response).join().timeout(
            const Duration(seconds: 8),
          );
      final body = jsonDecode(rawBody);
      if (response.statusCode >= 400) {
        throw ApiException(body['error']?.toString() ?? 'Lỗi API',
            code: body['code']?.toString());
      }
      return Map<String, dynamic>.from(body);
    } on SocketException {
      throw ApiException(
          'Không kết nối được API $_baseUrl. Kiểm tra Internet và URL API.');
    } on TimeoutException {
      throw ApiException(
          'API $_baseUrl phản hồi quá chậm. Kiểm tra Internet và URL API.');
    } on HandshakeException {
      throw ApiException('Kết nối HTTPS không hợp lệ');
    } on HttpException catch (e) {
      throw ApiException(e.message);
    }
  }
}
