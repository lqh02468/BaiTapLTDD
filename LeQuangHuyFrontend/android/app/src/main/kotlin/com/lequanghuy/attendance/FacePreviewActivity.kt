package com.lequanghuy.attendance

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.SurfaceTexture
import android.hardware.Camera
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.view.Gravity
import android.view.Surface
import android.view.TextureView
import android.view.View
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

@Suppress("DEPRECATION")
class FacePreviewActivity : Activity(), TextureView.SurfaceTextureListener {
    private lateinit var preview: TextureView
    private lateinit var status: TextView
    private lateinit var retryButton: Button
    private var camera: Camera? = null
    private val handler = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()
    private val images = ArrayList<String>()
    private val permissionRequest = 74
    private val mode by lazy { intent.getStringExtra("mode") ?: "login" }
    private val baseUrl by lazy { intent.getStringExtra("baseUrl") ?: "" }
    private val credential by lazy { intent.getStringExtra("credential") ?: "" }
    private var scanning = false
    @Volatile private var uploading = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
            View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or
            View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY

        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        preview = TextureView(this).apply { surfaceTextureListener = this@FacePreviewActivity }
        root.addView(preview, FrameLayout.LayoutParams(-1, -1))
        root.addView(FaceGuide(this), FrameLayout.LayoutParams(-1, -1))
        val controls = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(24), dp(16), dp(24), dp(40))
            setBackgroundColor(0x99000000.toInt())
        }
        status = TextView(this).apply {
            text = "Đang mở camera trước..."
            textSize = 19f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            setPadding(0, 0, 0, dp(12))
        }
        controls.addView(status)
        controls.addView(TextView(this).apply {
            text = "Ảnh chỉ gửi đến API đã cấu hình để so khớp; không lưu ảnh gốc."
            textSize = 13f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        })
        retryButton = Button(this).apply {
            text = "Thử quét lại"
            visibility = View.GONE
            setOnClickListener { startScan() }
        }
        controls.addView(retryButton, LinearLayout.LayoutParams(-1, -2))
        controls.addView(Button(this).apply {
            text = "Hủy"
            setOnClickListener { finish() }
        }, LinearLayout.LayoutParams(-1, -2))
        root.addView(controls, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))
        setContentView(root)
    }

    override fun onResume() {
        super.onResume()
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.CAMERA), permissionRequest)
        } else if (preview.isAvailable) openCamera(preview.surfaceTexture)
    }

    override fun onPause() {
        handler.removeCallbacksAndMessages(null)
        scanning = false
        closeCamera()
        super.onPause()
    }

    override fun onDestroy() {
        worker.shutdownNow()
        super.onDestroy()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == permissionRequest) {
            if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
                if (preview.isAvailable) openCamera(preview.surfaceTexture)
            } else fail("Bạn cần cấp quyền camera để quét khuôn mặt")
        }
    }

    override fun onSurfaceTextureAvailable(surface: SurfaceTexture, width: Int, height: Int) {
        if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) openCamera(surface)
    }
    override fun onSurfaceTextureSizeChanged(surface: SurfaceTexture, width: Int, height: Int) {}
    override fun onSurfaceTextureUpdated(surface: SurfaceTexture) {}
    override fun onSurfaceTextureDestroyed(surface: SurfaceTexture): Boolean {
        closeCamera()
        return true
    }

    private fun openCamera(surface: SurfaceTexture?) {
        if (camera != null || surface == null || isFinishing) return
        try {
            val info = Camera.CameraInfo()
            val frontId = (0 until Camera.getNumberOfCameras()).firstOrNull { id ->
                Camera.getCameraInfo(id, info)
                info.facing == Camera.CameraInfo.CAMERA_FACING_FRONT
            } ?: run { fail("Điện thoại không có camera trước"); return }
            camera = Camera.open(frontId)
            val rotation = when (windowManager.defaultDisplay.rotation) {
                Surface.ROTATION_90 -> 90
                Surface.ROTATION_180 -> 180
                Surface.ROTATION_270 -> 270
                else -> 0
            }
            val degrees = (info.orientation + rotation) % 360
            camera!!.setDisplayOrientation((360 - degrees) % 360)
            camera!!.setPreviewTexture(surface)
            camera!!.startPreview()
            startScan()
        } catch (e: Exception) {
            closeCamera()
            fail("Không mở được camera trước: ${e.message ?: "lỗi camera"}")
        }
    }

    private fun startScan() {
        if (camera == null || uploading) return
        handler.removeCallbacksAndMessages(null)
        images.clear()
        retryButton.visibility = View.GONE
        scanning = true
        status.text = when (mode) {
            "enroll" -> "Nhìn thẳng camera để đăng ký khuôn mặt"
            "verify_checkin" -> "Nhìn thẳng camera để xác thực khuôn mặt"
            else -> "Nhìn thẳng camera để đăng nhập"
        }
        handler.postDelayed({ capture() }, 1500)
    }

    private fun capture() {
        if (!scanning || camera == null || isFinishing) return
        try {
            val source = preview.bitmap ?: throw IllegalStateException("Chưa có hình ảnh camera")
            // Keep the camera image's proportions. Scaling the whole portrait preview
            // to 480x640 stretches faces on tall phone screens and hurts detection.
            val cropWidth = minOf(source.width, source.height * 3 / 4)
            val cropHeight = minOf(source.height, source.width * 4 / 3)
            val left = (source.width - cropWidth) / 2
            val centerY = (source.height * 0.43f).toInt()
            val top = (centerY - cropHeight / 2).coerceIn(0, source.height - cropHeight)
            val cropped = Bitmap.createBitmap(source, left, top, cropWidth, cropHeight)
            val bitmap = Bitmap.createScaledBitmap(cropped, 480, 640, true)
            val stream = ByteArrayOutputStream()
            bitmap.compress(Bitmap.CompressFormat.JPEG, 75, stream)
            if (bitmap !== cropped && bitmap !== source) bitmap.recycle()
            if (cropped !== source) cropped.recycle()
            source.recycle()
            images.add(Base64.encodeToString(stream.toByteArray(), Base64.NO_WRAP))
            val targetCount = if (mode == "enroll") 3 else 2
            if (images.size < targetCount) {
                status.text = if (mode != "enroll") "Quay đầu sang trái hoặc phải, giữ mặt trong khung"
                    else "Giữ mặt trong khung, nhìn thẳng camera (${images.size}/3)"
                handler.postDelayed({ capture() }, if (mode != "enroll") 2200 else 900)
            } else {
                scanning = false
                status.text = if (mode == "verify_checkin") "Đang nhận diện..." else "Đang so khớp khuôn mặt..."
                submit(ArrayList(images))
                images.clear()
            }
        } catch (e: Exception) { showRetry("Không lấy được hình ảnh camera: ${e.message}") }
    }

    private fun submit(captured: ArrayList<String>) {
        uploading = true
        worker.execute {
            var connection: HttpURLConnection? = null
            try {
                val path = when (mode) {
                    "enroll" -> "/me/face/enroll"
                    "verify_checkin" -> "/sessions/${intent.getLongExtra("sessionId", 0L)}/face-verify"
                    else -> "/auth/face/login"
                }
                connection = URL(baseUrl + path).openConnection() as HttpURLConnection
                connection.requestMethod = "POST"
                connection.connectTimeout = 8000
                connection.readTimeout = 20000
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                if (mode != "login") connection.setRequestProperty("Authorization", "Bearer $credential")
                val payload = JSONObject().put("images", JSONArray(captured))
                if (mode == "login") payload.put("identifier", credential)
                if (mode == "verify_checkin") {
                    payload.put("code", intent.getStringExtra("code") ?: "")
                }
                connection.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
                val response = if (connection.responseCode < 400) connection.inputStream else connection.errorStream
                val body = response.bufferedReader(Charsets.UTF_8).use { it.readText() }
                val json = JSONObject(body)
                if (connection.responseCode >= 400) throw IllegalStateException(json.optString("error", "Không nhận diện được"))
                val token = json.optString("token", "")
                if (mode == "login" && token.isEmpty()) throw IllegalStateException("API không trả phiên đăng nhập")
                if (mode == "verify_checkin" && json.optString("faceProof").isEmpty())
                    throw IllegalStateException("API không trả kết quả xác thực khuôn mặt")
                runOnUiThread {
                    if (!isFinishing) {
                        closeCamera()
                        val result = Intent().putExtra("token", token)
                        if (mode == "verify_checkin") {
                            status.text = "Nhận diện thành công"
                            result.putExtra("userId", json.optLong("userId"))
                                .putExtra("name", json.optString("name"))
                                .putExtra("studentCode", json.optString("studentCode"))
                                .putExtra("faceProof", json.optString("faceProof"))
                                .putExtra("expiresAt", json.optLong("expiresAt"))
                        }
                        setResult(RESULT_OK, result)
                        finish()
                    }
                }
            } catch (e: Exception) {
                runOnUiThread { if (!isFinishing) showRetry(e.message ?: "Không kết nối được API") }
            } finally {
                connection?.disconnect()
                captured.clear()
                uploading = false
            }
        }
    }

    private fun showRetry(message: String) {
        scanning = false
        images.clear()
        status.text = message
        retryButton.visibility = View.VISIBLE
    }

    private fun closeCamera() {
        try { camera?.stopPreview() } catch (_: Exception) {}
        camera?.release()
        camera = null
    }

    private fun fail(message: String) {
        setResult(RESULT_CANCELED, Intent().putExtra("error", message))
        finish()
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private class FaceGuide(context: Activity) : View(context) {
        private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            style = Paint.Style.STROKE
            strokeWidth = 4 * resources.displayMetrics.density
        }
        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            val w = width.toFloat()
            val h = height.toFloat()
            val radiusX = w * 0.37f
            val radiusY = minOf(h * 0.29f, radiusX * 1.35f)
            val centerY = h * 0.43f
            canvas.drawOval(w / 2 - radiusX, centerY - radiusY,
                w / 2 + radiusX, centerY + radiusY, paint)
        }
    }
}
