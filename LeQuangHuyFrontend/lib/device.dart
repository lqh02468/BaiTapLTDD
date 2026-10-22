import 'package:flutter/services.dart';

class DeviceServices {
  static const _channel = MethodChannel('lequanghuy/device');

  static Future<void> saveToken(String token) async {
    await _channel.invokeMethod<bool>('saveToken', {'token': token});
  }

  static Future<void> clearToken() async {
    await _channel.invokeMethod<bool>('clearToken');
  }

  static Future<String> biometricLogin() async {
    return await _channel.invokeMethod<String>('biometricLogin') ?? '';
  }

  static Future<String> faceLogin(String baseUrl, String identifier) async {
    return await _channel.invokeMethod<String>('faceLogin', {
          'baseUrl': baseUrl,
          'identifier': identifier,
        }) ??
        '';
  }

  static Future<void> faceEnroll(String baseUrl, String token) async {
    await _channel.invokeMethod<bool>('faceEnroll', {
      'baseUrl': baseUrl,
      'token': token,
    });
  }

  static Future<Map<String, dynamic>> faceVerifyCheckin(
      String baseUrl, String token, int sessionId, String code) async {
    final result =
        await _channel.invokeMapMethod<String, dynamic>('faceVerifyCheckin', {
      'baseUrl': baseUrl,
      'token': token,
      'sessionId': sessionId,
      'code': code,
    });
    return Map<String, dynamic>.from(result ?? {});
  }

  static Future<Map<String, double>> location() async {
    final result =
        await _channel.invokeMapMethod<String, double>('getLocation');
    if (result == null)
      throw PlatformException(code: 'location', message: 'Không có vị trí');
    return result;
  }

  static Future<void> openLocationSettings() async {
    await _channel.invokeMethod<bool>('openLocationSettings');
  }

  static Future<void> openAppSettings() async {
    await _channel.invokeMethod<bool>('openAppSettings');
  }
}
