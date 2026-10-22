import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'device.dart';

class LocationFailure implements Exception {
  final String message;
  const LocationFailure(this.message);

  @override
  String toString() => message;
}

/// Shared location flow for opening a session and confirming attendance.
class LocationService {
  static Future<Map<String, double>> getCurrentLocation(
      BuildContext context) async {
    try {
      return await DeviceServices.location();
    } on PlatformException catch (error) {
      debugPrint('Location error ${error.code}: ${error.message}');
      if (error.code == 'location_off' ||
          error.code == 'permission_denied_forever') {
        final isOff = error.code == 'location_off';
        final message = isOff
            ? 'Vui lòng bật định vị để tiếp tục.'
            : 'Quyền vị trí đã bị tắt. Vui lòng bật lại trong Cài đặt ứng dụng.';
        if (!context.mounted) throw LocationFailure(message);
        final openSettings = await showDialog<bool>(
              context: context,
              builder: (dialogContext) => AlertDialog(
                title: Text(isOff ? 'Bật định vị' : 'Cấp quyền vị trí'),
                content: Text(message),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(dialogContext, false),
                    child: const Text('Để sau'),
                  ),
                  FilledButton(
                    onPressed: () => Navigator.pop(dialogContext, true),
                    child: const Text('Mở cài đặt'),
                  ),
                ],
              ),
            ) ??
            false;
        if (!openSettings) throw LocationFailure(message);
        await _openSettingsAndWait(isOff
            ? DeviceServices.openLocationSettings
            : DeviceServices.openAppSettings);
        try {
          return await DeviceServices.location();
        } on PlatformException catch (retryError) {
          throw _failure(retryError);
        }
      }
      throw _failure(error);
    }
  }

  static LocationFailure _failure(PlatformException error) {
    switch (error.code) {
      case 'location_off':
        return const LocationFailure('Vui lòng bật định vị để tiếp tục.');
      case 'permission_denied':
        return const LocationFailure(
            'Ứng dụng cần quyền vị trí để sử dụng chức năng điểm danh.');
      case 'permission_denied_forever':
        return const LocationFailure(
            'Quyền vị trí đã bị tắt. Vui lòng bật lại trong Cài đặt ứng dụng.');
      case 'location_timeout':
        return const LocationFailure(
            'Không thể lấy vị trí hiện tại. Vui lòng kiểm tra GPS và thử lại.');
      case 'location_inaccurate':
        return const LocationFailure(
            'Tín hiệu vị trí chưa đủ chính xác. Hãy ra nơi thoáng và thử lại.');
      default:
        return LocationFailure(error.message ??
            'Không thể lấy vị trí hiện tại. Vui lòng thử lại.');
    }
  }

  static Future<void> _openSettingsAndWait(
      Future<void> Function() openSettings) async {
    final resumed = Completer<void>();
    final listener = AppLifecycleListener(onResume: () {
      if (!resumed.isCompleted) resumed.complete();
    });
    try {
      await openSettings();
      await resumed.future.timeout(const Duration(minutes: 2));
      await Future<void>.delayed(const Duration(milliseconds: 350));
    } on TimeoutException {
      throw const LocationFailure(
          'Chưa quay lại ứng dụng sau khi mở Cài đặt. Hãy thử lại.');
    } finally {
      listener.dispose();
    }
  }
}
