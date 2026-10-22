import 'package:flutter/material.dart';
import 'dart:io';
import 'dart:async';

import 'api.dart';
import 'api_config.dart';
import 'device.dart';
import 'location_service.dart';

void main() => runApp(const AttendanceApp());

final api = Api();

class AttendanceApp extends StatelessWidget {
  const AttendanceApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'LeQuangHuy Điểm danh',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff175cd3)),
          useMaterial3: true,
          inputDecorationTheme:
              const InputDecorationTheme(border: OutlineInputBorder()),
        ),
        home: const AuthPage(),
      );
}

void showError(BuildContext context, Object error) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$error')));
}

class AuthPage extends StatefulWidget {
  const AuthPage({super.key});
  @override
  State<AuthPage> createState() => _AuthPageState();
}

class _AuthPageState extends State<AuthPage> {
  final username = TextEditingController();
  final email = TextEditingController();
  final password = TextEditingController();
  final otp = TextEditingController();
  bool register = false;
  bool busy = false;
  int? challengeId;
  bool verifyingRegistration = false;

  Future<void> completeLogin(Map<String, dynamic> result) async {
    api.token = result['token'] as String;
    if (Platform.isAndroid) {
      try {
        await DeviceServices.saveToken(api.token!);
      } catch (_) {}
    }
    if (!mounted) return;
    Navigator.of(context).pushReplacement(MaterialPageRoute(
      builder: (_) => HomePage(user: Map<String, dynamic>.from(result['user'])),
    ));
  }

  Future<void> testConnection() async {
    setState(() => busy = true);
    try {
      await api.request('GET', '/health');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Kết nối API thành công')),
      );
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> submit() async {
    setState(() => busy = true);
    try {
      if (challengeId != null) {
        final result = await api.request('POST',
            verifyingRegistration ? '/auth/register/verify' : '/auth/verify', {
          'challengeId': challengeId,
          'code': otp.text.trim(),
        });
        if (verifyingRegistration) {
          if (!mounted) return;
          setState(() {
            challengeId = null;
            verifyingRegistration = false;
            register = false;
            otp.clear();
          });
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Đăng ký thành công. Hãy đăng nhập.')),
          );
          return;
        }
        await completeLogin(result);
      } else if (register) {
        final result = await api.request('POST', '/auth/register', {
          'username': username.text.trim(),
          'email': email.text.trim(),
          'password': password.text,
        });
        if (!mounted) return;
        setState(() {
          challengeId = result['challengeId'] as int;
          verifyingRegistration = true;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('OTP đã gửi đến email. Nhập mã để hoàn tất đăng ký.')),
        );
      } else {
        final result = await api.request('POST', '/auth/login', {
          'identifier': email.text.trim(),
          'password': password.text,
        });
        if (!mounted) return;
        if (result['token'] is String) {
          await completeLogin(result);
          return;
        }
        setState(() => challengeId = result['challengeId'] as int);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: const Text('OTP đã gửi đến email đã đăng ký'),
        ));
      }
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> biometricLogin({bool scanFace = false}) async {
    setState(() => busy = true);
    try {
      api.token = scanFace
          ? await DeviceServices.faceLogin(ApiConfig.baseUrl, email.text.trim())
          : await DeviceServices.biometricLogin();
      if (api.token == null || api.token!.isEmpty) {
        throw StateError('Không nhận được phiên đăng nhập');
      }
      if (scanFace) {
        try {
          await DeviceServices.saveToken(api.token!);
        } catch (_) {}
      }
      final user = await api.request('GET', '/me');
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => HomePage(user: user),
      ));
    } catch (e) {
      api.token = null;
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 430),
            child: ListView(
                padding: const EdgeInsets.all(24),
                shrinkWrap: true,
                children: [
                  const Icon(Icons.fact_check_rounded,
                      size: 68, color: Color(0xff175cd3)),
                  const SizedBox(height: 12),
                  Text('LeQuangHuy',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.headlineMedium),
                  const Text('Điểm danh sinh viên',
                      textAlign: TextAlign.center),
                  const SizedBox(height: 28),
                  if (challengeId != null)
                    TextField(
                        controller: otp,
                        keyboardType: TextInputType.number,
                        decoration:
                            const InputDecoration(labelText: 'Mã OTP 6 số'))
                  else ...[
                    if (register) ...[
                      TextField(
                          controller: username,
                          decoration: const InputDecoration(
                              labelText: 'Tên đăng nhập')),
                      const SizedBox(height: 12),
                    ],
                    TextField(
                        controller: email,
                        decoration: InputDecoration(
                            labelText:
                                register ? 'Email' : 'Username hoặc email')),
                    const SizedBox(height: 12),
                    TextField(
                        controller: password,
                        obscureText: true,
                        decoration:
                            const InputDecoration(labelText: 'Mật khẩu')),
                  ],
                  const SizedBox(height: 16),
                  FilledButton(
                      onPressed: busy ? null : submit,
                      child: Text(challengeId != null
                          ? 'Xác nhận OTP'
                          : register
                              ? 'Đăng ký'
                              : 'Đăng nhập')),
                  TextButton(
                    onPressed: busy
                        ? null
                        : () => setState(() {
                              challengeId = null;
                              verifyingRegistration = false;
                              register = !register;
                            }),
                    child: Text(register
                        ? 'Đã có tài khoản? Đăng nhập'
                        : 'Tạo tài khoản sinh viên'),
                  ),
                  if (Platform.isAndroid && !register && challengeId == null)
                    OutlinedButton.icon(
                        onPressed:
                            busy ? null : () => biometricLogin(scanFace: true),
                        icon: const Icon(Icons.camera_front_outlined),
                        label:
                            const Text('Quét khuôn mặt đã đăng ký trong app')),
                  if (Platform.isAndroid && !register && challengeId == null)
                    OutlinedButton.icon(
                        onPressed: busy ? null : () => biometricLogin(),
                        icon: const Icon(Icons.fingerprint),
                        label: const Text('Đăng nhập bằng sinh trắc học')),
                  const SizedBox(height: 16),
                  Text('API: ${ApiConfig.baseUrl}',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodySmall),
                  TextButton.icon(
                    onPressed: busy ? null : testConnection,
                    icon: const Icon(Icons.wifi_find),
                    label: const Text('Kiểm tra kết nối API'),
                  ),
                ]),
          ),
        ),
      );
}

class HomePage extends StatefulWidget {
  final Map<String, dynamic> user;
  const HomePage({super.key, required this.user});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  List<dynamic> classes = [];
  List<dynamic> users = [];
  Map<String, dynamic>? insights;
  bool faceEnrolled = false;
  bool loading = true;
  String get role => widget.user['role'] as String;

  @override
  void initState() {
    super.initState();
    refresh();
  }

  Future<void> refresh() async {
    try {
      final classResult = await api.request('GET', '/classes');
      final userResult =
          role == 'admin' ? await api.request('GET', '/users') : null;
      final insightResult =
          role == 'student' ? await api.request('GET', '/me/insights') : null;
      final faceResult =
          Platform.isAndroid ? await api.request('GET', '/me/face') : null;
      if (mounted)
        setState(() {
          classes = classResult['items'] as List<dynamic>;
          users = userResult?['items'] as List<dynamic>? ?? [];
          insights = insightResult;
          faceEnrolled = faceResult?['enrolled'] == true;
          loading = false;
        });
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  Future<String?> prompt(String title, String label) async {
    final controller = TextEditingController();
    return showDialog<String>(
        context: context,
        builder: (context) => AlertDialog(
              title: Text(title),
              content: TextField(
                  controller: controller,
                  autofocus: true,
                  decoration: InputDecoration(labelText: label)),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('Hủy')),
                FilledButton(
                    onPressed: () =>
                        Navigator.pop(context, controller.text.trim()),
                    child: const Text('Lưu')),
              ],
            ));
  }

  Future<void> classAction() async {
    final value = await prompt(role == 'student' ? 'Tham gia lớp' : 'Tạo lớp',
        role == 'student' ? 'Mã tham gia lớp' : 'Tên lớp');
    if (value == null || value.isEmpty) return;
    try {
      await api.request(
          'POST',
          role == 'student' ? '/classes/join' : '/classes',
          role == 'student' ? {'code': value} : {'name': value});
      await refresh();
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  Future<void> enrollFace() async {
    try {
      await DeviceServices.faceEnroll(ApiConfig.baseUrl, api.token!);
      await refresh();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
              content: Text('Đã đăng ký khuôn mặt để đăng nhập và điểm danh.')),
        );
      }
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  Future<void> removeFace() async {
    try {
      await api.request('DELETE', '/me/face');
      await refresh();
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
            title: Text('Xin chào, ${widget.user['username']}'),
            actions: [
              IconButton(
                  tooltip: 'Làm mới',
                  onPressed: refresh,
                  icon: const Icon(Icons.refresh)),
              IconButton(
                  tooltip: 'Đăng xuất',
                  onPressed: () async {
                    try {
                      await api.request('POST', '/auth/logout');
                    } catch (_) {}
                    if (Platform.isAndroid) {
                      try {
                        await DeviceServices.clearToken();
                      } catch (_) {}
                    }
                    api.token = null;
                    if (context.mounted)
                      Navigator.pushAndRemoveUntil(
                          context,
                          MaterialPageRoute(builder: (_) => const AuthPage()),
                          (_) => false);
                  },
                  icon: const Icon(Icons.logout)),
            ]),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: classAction,
          icon: const Icon(Icons.add),
          label: Text(role == 'student' ? 'Vào lớp' : 'Tạo lớp'),
        ),
        body: loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(padding: const EdgeInsets.all(16), children: [
                Card(
                    child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                                role == 'admin'
                                    ? 'Quản trị viên'
                                    : role == 'teacher'
                                        ? 'Giảng viên'
                                        : 'Sinh viên',
                                style: Theme.of(context).textTheme.titleLarge),
                            Text(widget.user['email'] as String),
                            const SizedBox(height: 8),
                            Text('${classes.length} lớp học'),
                          ],
                        ))),
                if (Platform.isAndroid)
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.face),
                      title: Text(faceEnrolled
                          ? 'Khuôn mặt đã đăng ký'
                          : 'Đăng ký khuôn mặt'),
                      subtitle: const Text(
                          'Dùng cùng mẫu cho đăng nhập và điểm danh khuôn mặt'),
                      onTap: enrollFace,
                      trailing: faceEnrolled
                          ? IconButton(
                              tooltip: 'Xóa mẫu khuôn mặt',
                              icon: const Icon(Icons.delete_outline),
                              onPressed: removeFace,
                            )
                          : null,
                    ),
                  ),
                if (insights != null)
                  Card(
                      child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Chuyên cần của bạn',
                              style: Theme.of(context).textTheme.titleMedium),
                          Text(insights!['rate'] == null
                              ? 'Chưa có buổi học đã kết thúc'
                              : 'Đã dự ${insights!['present']}/${insights!['completed']} buổi • ${insights!['rate']}%'),
                          if (insights!['atRisk'] == true)
                            const Text(
                                'Bạn đang dưới mức chuyên cần 80%. Hãy kiểm tra các buổi vắng.',
                                style: TextStyle(color: Colors.deepOrange)),
                          ...((insights!['missed'] as List<dynamic>).take(3))
                              .map((m) => Text(
                                  'Vắng: ${m['className']} • buổi #${m['sessionId']}')),
                        ]),
                  )),
                if (role == 'admin') ...[
                  const SizedBox(height: 14),
                  Text('Người dùng',
                      style: Theme.of(context).textTheme.titleLarge),
                  ...users.map((item) {
                    final u = Map<String, dynamic>.from(item);
                    return Card(
                        child: ListTile(
                      title: Text(u['username'] as String),
                      subtitle: Text('${u['email']} • ${u['role']}'),
                      trailing: PopupMenuButton<String>(
                          tooltip: 'Đổi vai trò',
                          onSelected: (value) async {
                            try {
                              await api.request(
                                  'PUT', '/users/${u['id']}', {'role': value});
                              await refresh();
                            } catch (e) {
                              if (context.mounted) showError(context, e);
                            }
                          },
                          itemBuilder: (_) => const [
                                PopupMenuItem(
                                    value: 'teacher',
                                    child: Text('Giảng viên')),
                                PopupMenuItem(
                                    value: 'student', child: Text('Sinh viên')),
                                PopupMenuItem(
                                    value: 'admin', child: Text('Admin')),
                              ]),
                    ));
                  }),
                ],
                const SizedBox(height: 14),
                Text('Lớp học', style: Theme.of(context).textTheme.titleLarge),
                if (classes.isEmpty)
                  const Padding(
                      padding: EdgeInsets.all(18),
                      child:
                          Text('Chưa có lớp. Chạm nút bên dưới để bắt đầu.')),
                ...classes.map((item) {
                  final cls = Map<String, dynamic>.from(item);
                  return Card(
                      child: ListTile(
                    leading: const Icon(Icons.school_outlined),
                    title: Text(cls['name'] as String),
                    subtitle: Text(role == 'student'
                        ? 'Nhấn để xem buổi điểm danh'
                        : 'Mã lớp: ${cls['join_code']}'),
                    onTap: () => Navigator.push(
                            context,
                            MaterialPageRoute(
                                builder: (_) =>
                                    ClassPage(cls: cls, role: role)))
                        .then((_) => refresh()),
                  ));
                }),
              ]),
      );
}

class ClassPage extends StatefulWidget {
  final Map<String, dynamic> cls;
  final String role;
  const ClassPage({super.key, required this.cls, required this.role});
  @override
  State<ClassPage> createState() => _ClassPageState();
}

class _ClassPageState extends State<ClassPage> {
  List<dynamic> sessions = [];
  bool openingSession = false;
  bool get teacher => widget.role != 'student';
  int get id => widget.cls['id'] as int;
  @override
  void initState() {
    super.initState();
    refresh();
  }

  Future<void> refresh() async {
    try {
      final result = await api.request('GET', '/classes/$id/sessions');
      if (mounted) setState(() => sessions = result['items'] as List<dynamic>);
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  Future<void> createSession() async {
    if (openingSession) return;
    setState(() => openingSession = true);
    try {
      final location = await LocationService.getCurrentLocation(context);
      if (!mounted) return;
      final result = await api.request('POST', '/classes/$id/sessions', {
        'minutes': 15,
        'latitude': location['latitude'],
        'longitude': location['longitude'],
        'radiusM': 100,
      });
      if (!mounted) return;
      await refresh();
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Mã điểm danh: ${result['code']} • bán kính 100m')));
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => openingSession = false);
    }
  }

  Future<void> editClass() async {
    final input = TextEditingController(text: widget.cls['name'] as String);
    final value = await showDialog<String>(
        context: context,
        builder: (context) => AlertDialog(
              title: const Text('Sửa tên lớp'),
              content: TextField(controller: input),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('Hủy')),
                FilledButton(
                    onPressed: () => Navigator.pop(context, input.text.trim()),
                    child: const Text('Lưu'))
              ],
            ));
    if (value == null || value.isEmpty) return;
    try {
      await api.request('PUT', '/classes/$id', {'name': value});
      if (mounted) setState(() => widget.cls['name'] = value);
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  Future<void> deleteClass() async {
    final yes = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
              title: const Text('Xóa lớp này?'),
              content: const Text('Các buổi và dữ liệu điểm danh sẽ bị xóa.'),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(context, false),
                    child: const Text('Hủy')),
                FilledButton(
                    onPressed: () => Navigator.pop(context, true),
                    child: const Text('Xóa'))
              ],
            ));
    if (yes != true) return;
    try {
      await api.request('DELETE', '/classes/$id');
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(widget.cls['name'] as String), actions: [
          IconButton(onPressed: refresh, icon: const Icon(Icons.refresh)),
          if (teacher)
            PopupMenuButton<String>(
                onSelected: (value) {
                  if (value == 'edit')
                    editClass();
                  else
                    deleteClass();
                },
                itemBuilder: (_) => const [
                      PopupMenuItem(value: 'edit', child: Text('Sửa lớp')),
                      PopupMenuItem(value: 'delete', child: Text('Xóa lớp')),
                    ]),
        ]),
        floatingActionButton: teacher
            ? FloatingActionButton.extended(
                onPressed: Platform.isAndroid && !openingSession
                    ? createSession
                    : null,
                icon: const Icon(Icons.add_alarm),
                label: Text(
                    openingSession ? 'Đang lấy vị trí...' : 'Mở điểm danh'))
            : null,
        body: ListView(padding: const EdgeInsets.all(16), children: [
          if (teacher)
            Card(
                child: ListTile(
                    title: const Text('Mã mời sinh viên'),
                    subtitle:
                        SelectableText(widget.cls['join_code'] as String))),
          Text('Buổi điểm danh', style: Theme.of(context).textTheme.titleLarge),
          if (sessions.isEmpty)
            const Padding(
                padding: EdgeInsets.all(16),
                child: Text('Chưa có buổi điểm danh.')),
          ...sessions.map((item) {
            final session = Map<String, dynamic>.from(item);
            final end = DateTime.fromMillisecondsSinceEpoch(
                (session['ends_at'] as int) * 1000);
            return Card(
                child: ListTile(
              title: Text('Buổi #${session['id']}'),
              subtitle: Text(
                  'Đến ${end.day}/${end.month} ${end.hour}:${end.minute.toString().padLeft(2, '0')}'),
              trailing: teacher
                  ? SelectableText('Mã: ${session['code']}')
                  : const Icon(Icons.chevron_right),
              onTap: teacher
                  ? () => Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => AttendancePage(session: session)))
                  : () => Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => CheckinPage(session: session))),
            ));
          }),
        ]),
      );
}

class CheckinPage extends StatefulWidget {
  final Map<String, dynamic> session;
  const CheckinPage({super.key, required this.session});
  @override
  State<CheckinPage> createState() => _CheckinPageState();
}

class _CheckinPageState extends State<CheckinPage> {
  final code = TextEditingController();
  bool busy = false;
  bool statusLoading = true;
  Map<String, dynamic>? attendanceStatus;
  String? statusError;
  String? faceProof;
  String? verifiedCode;
  int? verifiedUserId;
  int? proofExpiresAt;
  String? verifiedName;
  String? verifiedStudentCode;
  Timer? proofTimer;

  int get sessionId => (widget.session['id'] as num).toInt();
  bool get codeValid => RegExp(r'^\d{6}$').hasMatch(code.text.trim());
  bool get faceVerified =>
      faceProof != null &&
      verifiedCode == code.text.trim() &&
      (proofExpiresAt ?? 0) > DateTime.now().millisecondsSinceEpoch ~/ 1000;

  @override
  void initState() {
    super.initState();
    refreshStatus();
  }

  @override
  void dispose() {
    proofTimer?.cancel();
    code.dispose();
    super.dispose();
  }

  void clearFaceVerification() {
    proofTimer?.cancel();
    faceProof = null;
    verifiedCode = null;
    verifiedUserId = null;
    proofExpiresAt = null;
    verifiedName = null;
    verifiedStudentCode = null;
  }

  Future<void> refreshStatus() async {
    setState(() {
      statusLoading = true;
      statusError = null;
    });
    try {
      final result =
          await api.request('GET', '/sessions/$sessionId/attendance/status');
      if (mounted) {
        setState(() {
          attendanceStatus = result;
          if (result['hasAttended'] == true) clearFaceVerification();
        });
      }
    } catch (e) {
      if (mounted) setState(() => statusError = e.toString());
    } finally {
      if (mounted) setState(() => statusLoading = false);
    }
  }

  Future<void> handleCheckinError(Object error) async {
    if (error is ApiException && error.code == 'ALREADY_ATTENDED') {
      await refreshStatus();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Bạn đã điểm danh buổi này rồi.')));
      }
      return;
    }
    if (mounted) showError(context, error);
  }

  Future<void> verifyFace() async {
    if (busy) return;
    setState(() => busy = true);
    try {
      if (!codeValid) throw ApiException('Nhập mã điểm danh 6 số');
      final submittedCode = code.text.trim();
      await api.request('POST', '/sessions/$sessionId/code/validate',
          {'code': submittedCode});
      final result = await DeviceServices.faceVerifyCheckin(
          ApiConfig.baseUrl, api.token!, sessionId, submittedCode);
      if (result['faceProof'] == null ||
          result['faceProof'].toString().isEmpty) {
        throw ApiException('Chưa nhận được kết quả xác thực khuôn mặt');
      }
      if (submittedCode != code.text.trim()) return;
      if (!mounted) return;
      final expiresAt = (result['expiresAt'] as num).toInt();
      setState(() {
        clearFaceVerification();
        faceProof = result['faceProof'] as String;
        verifiedCode = submittedCode;
        verifiedUserId = (result['userId'] as num).toInt();
        proofExpiresAt = expiresAt;
        verifiedName = result['name'] as String?;
        verifiedStudentCode = result['studentCode'] as String?;
      });
      proofTimer = Timer(
        Duration(
            seconds: (expiresAt - DateTime.now().millisecondsSinceEpoch ~/ 1000)
                .clamp(1, 180)),
        () {
          if (mounted) setState(clearFaceVerification);
        },
      );
    } catch (e) {
      await handleCheckinError(e);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> confirmCheckin() async {
    if (busy || !codeValid || !faceVerified) return;
    setState(() => busy = true);
    try {
      final location = await LocationService.getCurrentLocation(context);
      final result = await api.request('POST', '/sessions/$sessionId/checkin', {
        'userId': verifiedUserId,
        'code': code.text.trim(),
        'faceVerified': true,
        'faceProof': faceProof,
        'latitude': location['latitude'],
        'longitude': location['longitude'],
      });
      if (!mounted) return;
      setState(() {
        clearFaceVerification();
        attendanceStatus = {...result, 'hasAttended': true};
      });
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Điểm danh thành công')));
    } catch (e) {
      await handleCheckinError(e);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Điểm danh'), actions: [
          IconButton(
              tooltip: 'Làm mới trạng thái',
              onPressed: refreshStatus,
              icon: const Icon(Icons.refresh)),
        ]),
        body: statusLoading
            ? const Center(child: CircularProgressIndicator())
            : statusError != null
                ? Center(
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Text(statusError!, textAlign: TextAlign.center),
                    TextButton(
                        onPressed: refreshStatus, child: const Text('Thử lại')),
                  ]))
                : attendanceStatus?['hasAttended'] == true
                    ? Center(
                        child: Card(
                          margin: const EdgeInsets.all(20),
                          child: Padding(
                            padding: const EdgeInsets.all(24),
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Icon(Icons.check_circle,
                                    size: 64, color: Colors.green),
                                const SizedBox(height: 12),
                                Text('Đã điểm danh',
                                    style: Theme.of(context)
                                        .textTheme
                                        .headlineSmall),
                                const SizedBox(height: 10),
                                Text(
                                    'Trạng thái: ${attendanceStatus!['status']}'),
                                Text(
                                    'Thời gian: ${DateTime.fromMillisecondsSinceEpoch(((attendanceStatus!['checkedAt'] as num).toInt() * 1000)).toString().substring(0, 16)}'),
                                Text(
                                    'Mã sinh viên: ${attendanceStatus!['studentCode']}'),
                              ],
                            ),
                          ),
                        ),
                      )
                    : ListView(padding: const EdgeInsets.all(20), children: [
                        const Text('Nhập mã do giảng viên cung cấp.'),
                        const SizedBox(height: 14),
                        TextField(
                          controller: code,
                          keyboardType: TextInputType.number,
                          maxLength: 6,
                          onChanged: (value) => setState(() {
                            if (value.trim() != verifiedCode) {
                              clearFaceVerification();
                            }
                          }),
                          decoration: const InputDecoration(
                              labelText: 'Mã điểm danh 6 số'),
                        ),
                        const SizedBox(height: 12),
                        OutlinedButton.icon(
                          onPressed: Platform.isAndroid && !busy && codeValid
                              ? verifyFace
                              : null,
                          icon: const Icon(Icons.face_retouching_natural),
                          label: const Text('Quét khuôn mặt'),
                        ),
                        if (faceVerified) ...[
                          const SizedBox(height: 8),
                          Text('Xác thực khuôn mặt thành công: '
                              '${verifiedName ?? ''} • ${verifiedStudentCode ?? ''}'),
                        ],
                        const SizedBox(height: 12),
                        const Text(
                            'Vị trí sẽ được kiểm tra khi xác nhận điểm danh.'),
                        const SizedBox(height: 16),
                        FilledButton(
                          onPressed: !busy && codeValid && faceVerified
                              ? confirmCheckin
                              : null,
                          child: const Text('Xác nhận điểm danh'),
                        ),
                      ]),
      );
}

class AttendancePage extends StatefulWidget {
  final Map<String, dynamic> session;
  const AttendancePage({super.key, required this.session});
  @override
  State<AttendancePage> createState() => _AttendancePageState();
}

class _AttendancePageState extends State<AttendancePage> {
  List<dynamic> items = [];
  @override
  void initState() {
    super.initState();
    refresh();
  }

  Future<void> refresh() async {
    try {
      final result = await api.request(
          'GET', '/sessions/${widget.session['id']}/attendance');
      if (mounted) setState(() => items = result['items'] as List<dynamic>);
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Danh sách điểm danh'), actions: [
          IconButton(onPressed: refresh, icon: const Icon(Icons.refresh))
        ]),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          Card(
              child: ListTile(
                  title: Text('Mã: ${widget.session['code']}'),
                  subtitle: Text('${items.length} sinh viên đã điểm danh'))),
          ...items.map((item) => Card(
                  child: ListTile(
                leading: const Icon(Icons.check_circle, color: Colors.green),
                title: Text(item['username'] as String),
                subtitle: Text(item['email'] as String),
              ))),
        ]),
      );
}
