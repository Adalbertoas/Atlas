import 'dart:typed_data';

import 'package:atlas_tablet/core/api.dart';
import 'package:atlas_tablet/core/config.dart';
import 'package:atlas_tablet/core/models.dart';
import 'package:atlas_tablet/screens/connect_screen.dart';
import 'package:atlas_tablet/ui/markdown.dart';
import 'package:atlas_tablet/ui/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('las horas del backend sin zona se toman como UTC', () {
    final parsed = parseServerTime('2026-11-18T18:21:24.850470')!;
    expect(parsed.toUtc(), DateTime.utc(2026, 11, 18, 18, 21, 24, 850, 470));
    expect(parseServerTime('2026-11-18T18:00:00Z')!.toUtc().hour, 18);
    expect(parseServerTime(null), isNull);
  });

  test('la respuesta del chat trae archivos y confirmaciones', () {
    final reply = ChatReply.fromJson({
      'reply': 'Listo',
      'conversation_id': 'c1',
      'requires_confirmation': false,
      'files': [
        {'name': 'Factura 120.xlsx', 'mime_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'size': 6813, 'path': 'D:/x'},
      ],
    });
    expect(reply.needsConfirmation, isFalse);
    expect(reply.files.single.isSpreadsheet, isTrue);
    expect(reply.files.single.sizeLabel, '7 KB');

    final pending = ChatReply.fromJson({'reply': null, 'requires_confirmation': true, 'confirmation_id': 'abc'});
    expect(pending.confirmationId, 'abc');
  });

  test('los adjuntos van en base64 con su tipo', () {
    final json = ChatAttachment(name: 'f.jpg', mimeType: 'image/jpeg', bytes: Uint8List.fromList([1, 2, 3])).toJson();
    expect(json, {'name': 'f.jpg', 'mime_type': 'image/jpeg', 'data': 'AQID'});
  });

  test('la huella se muestra en grupos de 4', () {
    expect(AtlasApi.prettyFingerprint('9e2926313d58'), '9E29 2631 3D58');
  });

  testWidgets('el markdown muestra negritas y viñetas', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: MarkdownText('**Total:** 36,260.29\n- 8 productos'))));
    expect(find.textContaining('Total:', findRichText: true), findsOneWidget);
    expect(find.text('•'), findsOneWidget);
  });

  testWidgets('la pantalla de conexión propone la IP de la PC', (tester) async {
    await tester.pumpWidget(MaterialApp(theme: atlasTheme(), home: ConnectScreen(onConnected: (ServerConfig _) {})));
    expect(find.text('https://atlas.sirinetrd.com'), findsOneWidget);
    expect(find.text('Conectar'), findsOneWidget);
  });
}
