import 'dart:convert';
import 'dart:io';

import '../lib/api.dart';

Future<void> main() async {
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  server.listen((request) async {
    if (request.uri.path != '/test') {
      request.response.statusCode = HttpStatus.notFound;
    } else {
      final contentLength = request.headers.contentLength;
      final body = await utf8.decoder.bind(request).join();
      if (contentLength != utf8.encode(body).length ||
          jsonDecode(body)['username'] != 'student') {
        request.response.statusCode = HttpStatus.badRequest;
        request.response.write('{"error":"JSON POST không hợp lệ"}');
      } else {
        request.response.headers.contentType = ContentType.json;
        request.response.write('{"ok":true}');
      }
    }
    await request.response.close();
  });

  try {
    final api = Api(baseUrl: 'http://127.0.0.1:${server.port}');
    final result = await api.request('POST', '/test', {'username': 'student'});
    if (result['ok'] != true) throw StateError('API POST không thành công');
    print('API JSON POST: OK');
  } finally {
    await server.close(force: true);
  }
}
