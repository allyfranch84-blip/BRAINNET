export function visibleChatMessages(messages, count) {
  return messages.slice(-count);
}

export function chatHistoryText(messages) {
  return messages.map((message) => `${message.role === 'ai' ? 'BRAINNET' : 'Você'}: ${message.text}`).join('\n\n');
}
