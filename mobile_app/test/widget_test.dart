// Smoke test: sin login guardado, la app debe arrancar en LoginScreen.
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:atlas_mobile/main.dart';

void main() {
  testWidgets('Arranca en la pantalla de login sin sesión guardada', (WidgetTester tester) async {
    // SharedPreferences necesita valores mockeados en tests — sin esto,
    // ApiClient.loadFromStorage() explota con MissingPluginException (no
    // hay plugin nativo real corriendo en el harness de widget tests).
    SharedPreferences.setMockInitialValues({});

    await tester.pumpWidget(const AtlasApp());
    await tester.pumpAndSettle();

    expect(find.text('ATLAS'), findsOneWidget);
    expect(find.text('Entrar'), findsOneWidget);
  });
}
