#!/usr/bin/env node
/**
 * Stop hook: checks if the last assistant response asked for a manual TD action
 * without discussing automation. Uses Anthropic API and strips trailing reasoning
 * from the response, outputting only clean JSON.
 */

const https = require('https');

const CONTINUE = JSON.stringify({ continue: true });
const BLOCK = JSON.stringify({
  hookSpecificOutput: {
    hookEventName: 'Stop',
    additionalContext:
      'REMINDER: Before finishing this response, reconsider the manual action you just asked the user to do. ' +
      'Ask yourself: Is this something the user will potentially do repeatedly? ' +
      'Could this be implemented as a UI control (button, slider, toggle) or happen automatically inside a script already in TouchDesigner? ' +
      'If yes to both, think of 2-3 concrete approaches and ask the user which they prefer before proceeding.',
  },
  continue: false,
});

async function callClaude(lastAssistantMessage) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    // No key — silently pass through
    process.stdout.write(CONTINUE);
    process.exit(0);
  }

  const body = JSON.stringify({
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 16,
    messages: [
      {
        role: 'user',
        content:
          'Did this assistant response ask the user to manually perform an action inside TouchDesigner ' +
          '(click a button, open a dialog, drag an operator, change a parameter, navigate a menu) ' +
          'WITHOUT already discussing whether this could be automated?\n\n' +
          'Reply with exactly one word: YES or NO.\n\n' +
          'Response to evaluate:\n"""\n' +
          lastAssistantMessage.slice(0, 4000) +
          '\n"""',
      },
    ],
  });

  return new Promise((resolve, reject) => {
    const req = https.request(
      {
        hostname: 'api.anthropic.com',
        path: '/v1/messages',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01',
          'Content-Length': Buffer.byteLength(body),
        },
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          try {
            const parsed = JSON.parse(data);
            const text = parsed?.content?.[0]?.text?.trim().toUpperCase() || '';
            resolve(text.startsWith('YES'));
          } catch {
            resolve(false);
          }
        });
      }
    );
    req.on('error', () => resolve(false));
    req.setTimeout(8000, () => { req.destroy(); resolve(false); });
    req.write(body);
    req.end();
  });
}

async function main() {
  let raw = '';
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) raw += chunk;

  let lastAssistantMessage = '';
  try {
    const input = JSON.parse(raw);
    // Hook input has transcript array; find last assistant message
    const msgs = input?.transcript || input?.messages || [];
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i]?.role === 'assistant') {
        const content = msgs[i].content;
        if (typeof content === 'string') {
          lastAssistantMessage = content;
        } else if (Array.isArray(content)) {
          lastAssistantMessage = content
            .filter((b) => b.type === 'text')
            .map((b) => b.text)
            .join('\n');
        }
        break;
      }
    }
  } catch {
    // Malformed input — pass through
    process.stdout.write(CONTINUE);
    process.exit(0);
  }

  if (!lastAssistantMessage) {
    process.stdout.write(CONTINUE);
    process.exit(0);
  }

  const isManualAction = await callClaude(lastAssistantMessage);
  process.stdout.write(isManualAction ? BLOCK : CONTINUE);
}

main().catch(() => {
  process.stdout.write(CONTINUE);
});
