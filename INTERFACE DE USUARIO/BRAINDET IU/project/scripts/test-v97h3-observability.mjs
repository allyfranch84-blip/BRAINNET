import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const shell=readFileSync('src/components/MasterShell_(1).jsx','utf8');
const dashboard=readFileSync('src/components/TelemetryDashboard.jsx','utf8');

test('chat mantém seletor e telemetria permanece sob demanda', () => {
  assert.match(shell,/lazy\(\(\) => import\("\.\/TelemetryDashboard"\)\)/);
  assert.match(shell,/FAST.*BALANCED.*DEEP.*AUTO/);
  assert.doesNotMatch(shell, /id="brainnet-telemetry"/);
});

test('painel solicita snapshot e indica ausência de GPU', () => {
  assert.match(dashboard,/get_runtime_telemetry/);
  assert.match(dashboard,/gpu_pct/);
  assert.match(dashboard,/Não disponível/);
});
