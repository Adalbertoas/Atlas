/// Espejo de MemoryOut (backend/app/memory/schemas.py).
class MemoryEntry {
  final int id;
  final String category;
  final String content;
  final List<String> tags;
  final DateTime createdAt;

  MemoryEntry({
    required this.id,
    required this.category,
    required this.content,
    required this.tags,
    required this.createdAt,
  });

  factory MemoryEntry.fromJson(Map<String, dynamic> json) {
    return MemoryEntry(
      id: json['id'] as int,
      category: json['category'] as String? ?? 'personal',
      content: json['content'] as String,
      tags: (json['tags'] as List? ?? []).cast<String>(),
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
    );
  }
}
