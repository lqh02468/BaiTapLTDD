using Microsoft.Data.Sqlite;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();
var databasePath = Environment.GetEnvironmentVariable("ATTENDANCE_DB")
    ?? Path.GetFullPath(Path.Combine(app.Environment.ContentRootPath, "..", "LeQuangHuyBackend", "attendance.db"));
var threshold = double.TryParse(Environment.GetEnvironmentVariable("FACE_SIMILARITY_THRESHOLD"), out var configured)
    ? configured : 0.42;
if (threshold is < 0.2 or > 0.9) throw new InvalidOperationException("FACE_SIMILARITY_THRESHOLD must be 0.2-0.9");

SqliteConnection OpenDb()
{
    var connection = new SqliteConnection($"Data Source={databasePath};Pooling=True;Default Timeout=10");
    connection.Open();
    using var pragma = connection.CreateCommand();
    pragma.CommandText = "PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000";
    pragma.ExecuteNonQuery();
    return connection;
}

using (var db = OpenDb())
using (var command = db.CreateCommand())
{
    command.CommandText = """
        CREATE TABLE IF NOT EXISTS face_profiles (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            face_embedding TEXT NOT NULL,
            face_image_path TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """;
    command.ExecuteNonQuery();
}

app.MapGet("/health", () => Results.Ok(new { status = "ok", service = "LeQuangHuyApi" }));

app.MapGet("/api/face/profile", (HttpContext context) =>
{
    using var db = OpenDb();
    var actor = Actor(context, db);
    if (actor is null) return Results.Unauthorized();
    using var cmd = db.CreateCommand();
    cmd.CommandText = "SELECT id,created_at,updated_at FROM face_profiles WHERE user_id=$user";
    cmd.Parameters.AddWithValue("$user", actor.Id);
    using var reader = cmd.ExecuteReader();
    return reader.Read()
        ? Results.Ok(new { enrolled = true, id = reader.GetInt64(0), createdAt = reader.GetInt64(1), updatedAt = reader.GetInt64(2) })
        : Results.Ok(new { enrolled = false });
});

app.MapPost("/api/face/profile", (HttpContext context, FaceProfileInput input) =>
{
    using var db = OpenDb();
    var actor = Actor(context, db);
    if (actor is null) return Results.Unauthorized();
    if (!ValidEmbedding(input.FaceEmbedding)) return Results.BadRequest(new { error = "Embedding phải có 128 số hữu hạn và được chuẩn hóa" });
    if (input.FaceImagePath?.Length > 500) return Results.BadRequest(new { error = "Đường dẫn ảnh quá dài" });
    var now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
    using var cmd = db.CreateCommand();
    cmd.CommandText = """
        INSERT INTO face_profiles(user_id,face_embedding,face_image_path,created_at,updated_at)
        VALUES($user,$embedding,$image,$now,$now)
        ON CONFLICT(user_id) DO UPDATE SET
            face_embedding=excluded.face_embedding,
            face_image_path=excluded.face_image_path,
            updated_at=excluded.updated_at
        """;
    cmd.Parameters.AddWithValue("$user", actor.Id);
    cmd.Parameters.AddWithValue("$embedding", JsonSerializer.Serialize(input.FaceEmbedding));
    cmd.Parameters.AddWithValue("$image", (object?)input.FaceImagePath ?? DBNull.Value);
    cmd.Parameters.AddWithValue("$now", now);
    cmd.ExecuteNonQuery();
    return Results.Ok(new { message = "Đã lưu FaceProfile", userId = actor.Id });
});

app.MapDelete("/api/face/profile", (HttpContext context) =>
{
    using var db = OpenDb();
    var actor = Actor(context, db);
    if (actor is null) return Results.Unauthorized();
    using var cmd = db.CreateCommand();
    cmd.CommandText = "DELETE FROM face_profiles WHERE user_id=$user";
    cmd.Parameters.AddWithValue("$user", actor.Id);
    cmd.ExecuteNonQuery();
    return Results.Ok(new { message = "Đã xóa FaceProfile" });
});

app.MapPost("/api/face/recognize", (HttpContext context, FaceRecognitionInput input) =>
{
    using var db = OpenDb();
    var actor = Actor(context, db);
    if (actor is null) return Results.Unauthorized();
    if (!ValidEmbedding(input.FaceEmbedding)) return Results.BadRequest(new { error = "Embedding không hợp lệ" });
    using var cmd = db.CreateCommand();
    cmd.CommandText = """
        SELECT users.id,users.username,users.student_code,face_profiles.face_embedding
        FROM face_profiles JOIN users ON users.id=face_profiles.user_id
        WHERE ($student=0 OR face_profiles.user_id=$actor)
        """;
    cmd.Parameters.AddWithValue("$student", actor.Role == "student" ? 1 : 0);
    cmd.Parameters.AddWithValue("$actor", actor.Id);
    using var reader = cmd.ExecuteReader();
    (long id, string name, string studentCode, double similarity)? best = null;
    while (reader.Read())
    {
        var enrolled = JsonSerializer.Deserialize<double[]>(reader.GetString(3));
        if (!ValidEmbedding(enrolled)) continue;
        var similarity = Cosine(input.FaceEmbedding, enrolled!);
        if (best is null || similarity > best.Value.similarity)
            best = (reader.GetInt64(0), reader.GetString(1), reader.IsDBNull(2) ? $"SV{reader.GetInt64(0):D6}" : reader.GetString(2), similarity);
    }
    if (best is null || best.Value.similarity < threshold)
        return Results.Ok(new { recognized = false, similarity = Math.Round(Math.Max(0, best?.similarity ?? 0) * 100, 1) });
    return Results.Ok(new {
        recognized = true, userId = best.Value.id, name = best.Value.name,
        studentCode = best.Value.studentCode,
        similarity = Math.Round(best.Value.similarity * 100, 1),
        status = "Nhận diện thành công"
    });
});

app.Run();

static bool ValidEmbedding(double[]? values)
{
    if (values is null || values.Length != 128 || values.Any(x => !double.IsFinite(x))) return false;
    var norm = Math.Sqrt(values.Sum(x => x * x));
    return norm is >= 0.95 and <= 1.05;
}

static double Cosine(double[] a, double[] b)
{
    var dot = 0.0;
    for (var i = 0; i < a.Length; i++) dot += a[i] * b[i];
    return dot;
}

static AppUser? Actor(HttpContext context, SqliteConnection db)
{
    var authorization = context.Request.Headers.Authorization.ToString();
    if (!authorization.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase)) return null;
    var token = authorization[7..].Trim();
    if (token.Length < 20) return null;
    var digest = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(token)));
    using var cmd = db.CreateCommand();
    cmd.CommandText = """
        SELECT users.id,users.role FROM tokens
        JOIN users ON users.id=tokens.user_id
        WHERE token_hash=$hash AND expires_at>$now
        """;
    cmd.Parameters.AddWithValue("$hash", digest);
    cmd.Parameters.AddWithValue("$now", DateTimeOffset.UtcNow.ToUnixTimeSeconds());
    using var reader = cmd.ExecuteReader();
    return reader.Read() ? new AppUser(reader.GetInt64(0), reader.GetString(1)) : null;
}

record AppUser(long Id, string Role);
record FaceProfileInput(double[] FaceEmbedding, string? FaceImagePath);
record FaceRecognitionInput(double[] FaceEmbedding);
record FaceProfile(long Id, long UserId, string FaceEmbedding, string? FaceImagePath, long CreatedAt, long UpdatedAt);
