package com.lequanghuy.attendance

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.biometrics.BiometricPrompt
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.os.CancellationSignal
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.provider.Settings
import android.net.Uri
import android.util.Base64
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.security.KeyStore
import java.util.concurrent.atomic.AtomicBoolean
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class MainActivity : FlutterActivity() {
    private val channelName = "lequanghuy/device"
    private val prefs by lazy { getSharedPreferences("secure_session", Context.MODE_PRIVATE) }
    private var pendingLocation: MethodChannel.Result? = null
    private var activeLocationManager: LocationManager? = null
    private var activeLocationListener: LocationListener? = null
    private var locationTimeout: Runnable? = null
    private val locationHandler = Handler(Looper.getMainLooper())
    private var pendingFaceRequest: MethodChannel.Result? = null
    private var pendingFaceMode: String? = null
    private val facePreviewRequest = 73

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName).setMethodCallHandler { call, result ->
            when (call.method) {
                "saveToken" -> {
                    try {
                        saveToken(call.argument<String>("token") ?: "")
                        result.success(true)
                    } catch (e: Exception) { result.error("storage", e.message, null) }
                }
                "clearToken" -> {
                    prefs.edit().clear().apply()
                    result.success(true)
                }
                "biometricLogin" -> biometricLogin(result)
                "faceLogin" -> openFaceScan("login", call.argument<String>("baseUrl") ?: "",
                    call.argument<String>("identifier") ?: "", result)
                "faceEnroll" -> openFaceScan("enroll", call.argument<String>("baseUrl") ?: "",
                    call.argument<String>("token") ?: "", result)
                "faceVerifyCheckin" -> openFaceScan("verify_checkin", call.argument<String>("baseUrl") ?: "",
                    call.argument<String>("token") ?: "", result,
                    call.argument<Number>("sessionId")?.toLong() ?: 0L,
                    call.argument<String>("code") ?: "")
                "getLocation" -> requestLocation(result)
                "openLocationSettings" -> {
                    try {
                        startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS))
                        result.success(true)
                    } catch (e: Exception) { result.error("location", e.message, null) }
                }
                "openAppSettings" -> {
                    try {
                        startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                            Uri.parse("package:$packageName")))
                        result.success(true)
                    } catch (e: Exception) { result.error("settings", e.message, null) }
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey("attendance_token", null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder("attendance_token",
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .build())
        return generator.generateKey()
    }

    private fun saveToken(token: String) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        prefs.edit()
            .putString("iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .putString("data", Base64.encodeToString(cipher.doFinal(token.toByteArray()), Base64.NO_WRAP))
            .apply()
    }

    private fun readToken(): String {
        val iv = Base64.decode(prefs.getString("iv", "") ?: "", Base64.NO_WRAP)
        val data = Base64.decode(prefs.getString("data", "") ?: "", Base64.NO_WRAP)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
        return String(cipher.doFinal(data), Charsets.UTF_8)
    }

    private fun biometricLogin(result: MethodChannel.Result) {
        if (!prefs.contains("data")) {
            result.error("not_enrolled", "Hãy đăng nhập bằng OTP trước", null)
            return
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
            result.error("unsupported", "Thiết bị cần Android 9 trở lên", null)
            return
        }
        try {
            val completed = AtomicBoolean(false)
            val prompt = BiometricPrompt.Builder(this)
                .setTitle("Đăng nhập LeQuangHuy")
                .setSubtitle("Dùng khuôn mặt hoặc vân tay đã đăng ký trên điện thoại")
                .setNegativeButton("Hủy", mainExecutor) { _, _ ->
                    if (completed.compareAndSet(false, true)) result.error("cancelled", "Đã hủy", null)
                }
                .build()
            prompt.authenticate(CancellationSignal(), mainExecutor,
                object : BiometricPrompt.AuthenticationCallback() {
                    override fun onAuthenticationSucceeded(authResult: BiometricPrompt.AuthenticationResult) {
                        if (completed.compareAndSet(false, true)) {
                            try { result.success(readToken()) }
                            catch (e: Exception) { result.error("storage", "Phiên lưu bị lỗi", null) }
                        }
                    }
                    override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                        if (completed.compareAndSet(false, true)) {
                            result.error("biometric", errString.toString(), null)
                        }
                    }
                })
        } catch (e: Exception) { result.error("biometric", e.message, null) }
    }

    private fun openFaceScan(mode: String, baseUrl: String, credential: String, result: MethodChannel.Result,
                             sessionId: Long = 0L, code: String = "") {
        if (!baseUrl.startsWith("http://") && !baseUrl.startsWith("https://")) {
            result.error("config", "URL API không hợp lệ", null)
            return
        }
        if (credential.isBlank()) {
            result.error("missing", if (mode == "login") "Nhập username hoặc email trước" else "Cần đăng nhập bằng OTP trước", null)
            return
        }
        if (mode == "verify_checkin" && (sessionId <= 0 || code.isBlank())) {
            result.error("missing", "Nhập mã điểm danh trước khi quét khuôn mặt", null)
            return
        }
        if (pendingFaceRequest != null) {
            result.error("busy", "Đang mở camera", null)
            return
        }
        pendingFaceRequest = result
        pendingFaceMode = mode
        try {
            val intent = Intent(this, FacePreviewActivity::class.java)
                .putExtra("mode", mode)
                .putExtra("baseUrl", baseUrl.trimEnd('/'))
                .putExtra("credential", credential)
                .putExtra("sessionId", sessionId)
                .putExtra("code", code)
            startActivityForResult(intent, facePreviewRequest)
        } catch (e: Exception) {
            pendingFaceRequest = null
            pendingFaceMode = null
            result.error("camera", e.message ?: "Không mở được camera", null)
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != facePreviewRequest) return
        val result = pendingFaceRequest ?: return
        pendingFaceRequest = null
        val mode = pendingFaceMode
        pendingFaceMode = null
        if (resultCode == RESULT_OK) {
            if (mode == "login") result.success(data?.getStringExtra("token"))
            else if (mode == "verify_checkin") {
                result.success(mapOf(
                    "userId" to (data?.getLongExtra("userId", 0L) ?: 0L),
                    "name" to (data?.getStringExtra("name") ?: ""),
                    "studentCode" to (data?.getStringExtra("studentCode") ?: ""),
                    "faceProof" to (data?.getStringExtra("faceProof") ?: ""),
                    "expiresAt" to (data?.getLongExtra("expiresAt", 0L) ?: 0L)))
            } else result.success(true)
        }
        else result.error("cancelled", data?.getStringExtra("error") ?: "Đã hủy", null)
    }

    private fun requestLocation(result: MethodChannel.Result) {
        if (pendingLocation != null) {
            result.error("busy", "Đang lấy vị trí", null)
            return
        }
        try {
            val manager = getSystemService(Context.LOCATION_SERVICE) as LocationManager
            if (!locationEnabled(manager)) {
                result.error("location_off", "Vui lòng bật định vị để tiếp tục.", null)
                return
            }
            pendingLocation = result
            if (!hasLocationPermission()) {
                val askedBefore = prefs.getBoolean("location_permission_requested", false)
                if (askedBefore && !shouldShowRequestPermissionRationale(Manifest.permission.ACCESS_FINE_LOCATION) &&
                    !shouldShowRequestPermissionRationale(Manifest.permission.ACCESS_COARSE_LOCATION)) {
                    finishLocation(null, "Quyền vị trí đã bị tắt. Vui lòng bật lại trong Cài đặt ứng dụng.",
                        "permission_denied_forever")
                    return
                }
                prefs.edit().putBoolean("location_permission_requested", true).apply()
                requestPermissions(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION), 42)
            } else fetchLocation()
        } catch (e: Exception) {
            pendingLocation = null
            result.error("location", "Không thể kiểm tra định vị: ${e.message}", null)
        }
    }

    private fun hasLocationPermission(): Boolean =
        checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
        checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    private fun locationEnabled(manager: LocationManager): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) manager.isLocationEnabled
        else manager.isProviderEnabled(LocationManager.GPS_PROVIDER) ||
             manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 42) {
            if (grantResults.any { it == PackageManager.PERMISSION_GRANTED }) fetchLocation()
            else {
                val permanent = !shouldShowRequestPermissionRationale(Manifest.permission.ACCESS_FINE_LOCATION) &&
                    !shouldShowRequestPermissionRationale(Manifest.permission.ACCESS_COARSE_LOCATION)
                finishLocation(null,
                    if (permanent) "Quyền vị trí đã bị tắt. Vui lòng bật lại trong Cài đặt ứng dụng."
                    else "Ứng dụng cần quyền vị trí để sử dụng chức năng điểm danh.",
                    if (permanent) "permission_denied_forever" else "permission_denied")
            }
        }
    }

    private fun fetchLocation() {
        try {
            val manager = getSystemService(Context.LOCATION_SERVICE) as LocationManager
            if (!locationEnabled(manager)) {
                finishLocation(null, "Vui lòng bật định vị để tiếp tục.", "location_off")
                return
            }
            val fineGranted = checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
            val providers = mutableListOf<String>()
            if (fineGranted && manager.isProviderEnabled(LocationManager.GPS_PROVIDER))
                providers.add(LocationManager.GPS_PROVIDER)
            if (manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER))
                providers.add(LocationManager.NETWORK_PROVIDER)
            if (providers.isEmpty()) {
                finishLocation(null, "Không có nguồn vị trí khả dụng. Hãy kiểm tra GPS và thử lại.",
                    "provider_unavailable")
                return
            }
            var best: Location? = null
            val freshAfter = SystemClock.elapsedRealtimeNanos() - 30_000_000_000L
            fun consider(location: Location) {
                if (location.elapsedRealtimeNanos < freshAfter) return
                if (best == null || (location.hasAccuracy() &&
                    (!best!!.hasAccuracy() || location.accuracy < best!!.accuracy))) best = location
                if (location.hasAccuracy() && location.accuracy <= 100f) finishLocation(location, null)
            }
            val listener = object : LocationListener {
                override fun onLocationChanged(location: Location) {
                    consider(location)
                }
                override fun onProviderEnabled(provider: String) {}
                override fun onProviderDisabled(provider: String) {
                    if (!locationEnabled(manager)) finishLocation(null,
                        "Vui lòng bật định vị để tiếp tục.", "location_off")
                }
                override fun onStatusChanged(provider: String, status: Int, extras: Bundle) {}
            }
            activeLocationManager = manager
            activeLocationListener = listener
            for (provider in providers) {
                if (pendingLocation == null) break
                manager.requestLocationUpdates(provider, 1000L, 0f, listener, Looper.getMainLooper())
                manager.getLastKnownLocation(provider)?.let { consider(it) }
            }
            if (pendingLocation == null) return
            val timeout = Runnable {
                if (pendingLocation != null) {
                    val candidate = best
                    if (candidate != null && candidate.hasAccuracy() && candidate.accuracy <= 150f)
                        finishLocation(candidate, null)
                    else finishLocation(null, if (candidate == null)
                        "Không thể lấy vị trí hiện tại. Vui lòng kiểm tra GPS và thử lại."
                        else "Tín hiệu vị trí chưa đủ chính xác. Hãy ra nơi thoáng và thử lại.",
                        if (candidate == null) "location_timeout" else "location_inaccurate")
                }
            }
            locationTimeout = timeout
            locationHandler.postDelayed(timeout, 30000)
        } catch (e: SecurityException) {
            finishLocation(null, "Ứng dụng cần quyền vị trí để sử dụng chức năng điểm danh.", "permission_denied")
        } catch (e: Exception) {
            finishLocation(null, "Không thể lấy vị trí hiện tại: ${e.message}", "location")
        }
    }

    private fun finishLocation(location: Location?, error: String?, code: String = "location") {
        val result = pendingLocation ?: return
        pendingLocation = null
        locationTimeout?.let { locationHandler.removeCallbacks(it) }
        locationTimeout = null
        activeLocationListener?.let { listener ->
            try { activeLocationManager?.removeUpdates(listener) } catch (_: Exception) {}
        }
        activeLocationListener = null
        activeLocationManager = null
        if (location != null) result.success(mapOf("latitude" to location.latitude,
            "longitude" to location.longitude))
        else result.error(code, error, null)
    }
}
