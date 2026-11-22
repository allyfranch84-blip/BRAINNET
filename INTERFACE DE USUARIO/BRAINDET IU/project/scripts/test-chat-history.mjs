import { test } from 'node:test';
import assert from 'node:assert/strict';
import { visibleChatMessages, chatHistoryText } from '../src/components/chatHistory.mjs';

test('histórico longo mostra as últimas mensagens sem descartar originais', () => {
  const messages = Array.from({length: 1000}, (_, i) => ({ role: 'user', text: `mensagem ${i}` }));
  const shown = visibleChatMessages(messages, 100);
  assert.equal(shown.length, 100);
  assert.equal(shown[0].text, 'mensagem 900');
  assert.equal(visibleChatMessages(messages, 200)[0].text, 'mensagem 800');
  assert.equal(messages.length, 1000);
  assert.match(chatHistoryText(messages), /mensagem 0\n/);
  assert.match(chatHistoryText(messages), /mensagem 999$/);
});
