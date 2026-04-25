import { spawn, execSync, ChildProcess } from 'child_process';
import { createInterface } from 'readline';
import fs from 'fs';
import path from 'path';

import { GROUPS_DIR } from '../config.js';
import { readEnvFile } from '../env.js';

const feishuEnv = readEnvFile(['FEISHU_LARK_CLI_PROFILE']);
const LARK_PROFILE =
  process.env.FEISHU_LARK_CLI_PROFILE ||
  feishuEnv.FEISHU_LARK_CLI_PROFILE ||
  '';
import { logger } from '../logger.js';
import { registerChannel, ChannelOpts } from './registry.js';
import {
  Channel,
  OnChatMetadata,
  OnInboundMessage,
  RegisteredGroup,
} from '../types.js';

interface FeishuEvent {
  type: string;
  id?: string;
  message_id?: string;
  chat_id?: string;
  chat_type?: string; // p2p | group
  message_type?: string;
  content?: string;
  sender_id?: string;
  create_time?: string;
  timestamp?: string;
}

/** Append --profile flag if configured. */
function profileArgs(): string[] {
  return LARK_PROFILE ? ['--profile', LARK_PROFILE] : [];
}

export class FeishuChannel implements Channel {
  name = 'feishu';

  private proc: ChildProcess | null = null;
  private connected = false;
  private opts: {
    onMessage: OnInboundMessage;
    onChatMetadata: OnChatMetadata;
    registeredGroups: () => Record<string, RegisteredGroup>;
  };
  private consecutiveErrors = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(opts: ChannelOpts) {
    this.opts = opts;
  }

  async connect(): Promise<void> {
    // Verify lark-cli is logged in
    try {
      execSync(
        `lark-cli auth status ${LARK_PROFILE ? `--profile ${LARK_PROFILE}` : ''}`,
        { stdio: 'ignore', timeout: 10000 },
      );
    } catch {
      logger.warn(
        'Feishu: lark-cli auth check failed. Run `lark-cli auth login --recommend` first.',
      );
      return;
    }

    this.startEventSubscription();
  }

  async sendMessage(jid: string, text: string): Promise<void> {
    if (!this.connected) {
      logger.warn('Feishu channel not connected');
      return;
    }

    const chatId = jid.replace(/^feishu:/, '');
    if (!chatId) {
      logger.warn({ jid }, 'Invalid Feishu JID');
      return;
    }

    try {
      // Write message to a temp approach via stdin to avoid shell escaping issues
      // Use --text for plain text messages
      const args = [
        'im',
        '+messages-send',
        '--as',
        'bot',
        ...profileArgs(),
        '--chat-id',
        chatId,
        '--text',
        text,
      ];

      await new Promise<void>((resolve, reject) => {
        const child = spawn('lark-cli', args, {
          stdio: ['ignore', 'pipe', 'pipe'],
          timeout: 30000,
        });

        let stderr = '';
        child.stderr?.on('data', (chunk: Buffer) => {
          stderr += chunk.toString();
        });

        child.on('close', (code) => {
          if (code === 0) {
            resolve();
          } else {
            reject(new Error(`lark-cli send failed (code ${code}): ${stderr}`));
          }
        });

        child.on('error', reject);
      });

      logger.info({ chatId }, 'Feishu message sent');
    } catch (err) {
      logger.error({ jid, err }, 'Failed to send Feishu message');
    }
  }

  async sendFile(jid: string, filePath: string): Promise<void> {
    if (!this.connected) {
      logger.warn('Feishu channel not connected, cannot send file');
      return;
    }

    const chatId = jid.replace(/^feishu:/, '');
    if (!chatId) {
      logger.warn({ jid }, 'Invalid Feishu JID for file send');
      return;
    }

    if (!fs.existsSync(filePath)) {
      logger.warn({ filePath }, 'File does not exist, cannot send');
      return;
    }

    try {
      // Detect file type for appropriate flag
      const ext = path.extname(filePath).toLowerCase();
      const isImage = [
        '.png',
        '.jpg',
        '.jpeg',
        '.gif',
        '.bmp',
        '.webp',
      ].includes(ext);
      const flag = isImage ? '--image' : '--file';

      // lark-cli requires relative paths — use cwd + basename
      const fileDir = path.dirname(filePath);
      const fileName = path.basename(filePath);

      const args = [
        'im',
        '+messages-send',
        '--as',
        'bot',
        ...profileArgs(),
        '--chat-id',
        chatId,
        flag,
        `./${fileName}`,
      ];

      await new Promise<void>((resolve, reject) => {
        const child = spawn('lark-cli', args, {
          cwd: fileDir,
          stdio: ['ignore', 'pipe', 'pipe'],
          timeout: 60000,
        });

        let stderr = '';
        child.stderr?.on('data', (chunk: Buffer) => {
          stderr += chunk.toString();
        });

        child.on('close', (code) => {
          if (code === 0) {
            resolve();
          } else {
            reject(
              new Error(`lark-cli file send failed (code ${code}): ${stderr}`),
            );
          }
        });

        child.on('error', reject);
      });

      logger.info({ chatId, filePath }, 'Feishu file sent');
    } catch (err) {
      logger.error({ jid, filePath, err }, 'Failed to send Feishu file');
    }
  }

  isConnected(): boolean {
    return this.connected;
  }

  ownsJid(jid: string): boolean {
    return jid.startsWith('feishu:');
  }

  async disconnect(): Promise<void> {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.killProc();
    this.connected = false;
    logger.info('Feishu channel stopped');
  }

  // --- Private ---

  private killProc(): void {
    if (this.proc) {
      this.proc.kill('SIGTERM');
      this.proc = null;
    }
  }

  private startEventSubscription(): void {
    this.killProc();

    const proc = spawn(
      'lark-cli',
      [
        'event',
        '+subscribe',
        ...profileArgs(),
        '--event-types',
        'im.message.receive_v1',
        '--compact',
        '--quiet',
        '--force',
      ],
      {
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    );

    this.proc = proc;

    // Read NDJSON lines from stdout
    const rl = createInterface({ input: proc.stdout! });
    rl.on('line', (line: string) => {
      try {
        const event: FeishuEvent = JSON.parse(line);
        this.processEvent(event);
      } catch (err) {
        logger.debug({ line, err }, 'Feishu: failed to parse event line');
      }
    });

    proc.stderr?.on('data', (chunk: Buffer) => {
      const msg = chunk.toString().trim();
      if (msg) {
        logger.debug({ msg }, 'Feishu event stderr');
      }
    });

    proc.on('close', (code) => {
      logger.warn({ code }, 'Feishu event subscription exited');
      this.connected = false;
      this.proc = null;
      this.scheduleReconnect();
    });

    proc.on('error', (err) => {
      logger.error({ err }, 'Feishu event subscription error');
      this.connected = false;
      this.proc = null;
      this.scheduleReconnect();
    });

    this.connected = true;
    this.consecutiveErrors = 0;
    logger.info('Feishu channel connected (event subscription started)');
  }

  private scheduleReconnect(): void {
    this.consecutiveErrors++;
    const backoffMs = Math.min(
      5000 * Math.pow(2, this.consecutiveErrors - 1),
      5 * 60 * 1000,
    );
    logger.info(
      { consecutiveErrors: this.consecutiveErrors, backoffMs },
      'Feishu: scheduling reconnect',
    );
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.startEventSubscription();
    }, backoffMs);
  }

  private processEvent(event: FeishuEvent): void {
    if (event.type !== 'im.message.receive_v1') return;
    if (!event.chat_id || !event.content) return;

    const chatJid = `feishu:${event.chat_id}`;
    const messageId = event.message_id || event.id || '';
    const timestamp = event.create_time
      ? new Date(parseInt(event.create_time, 10)).toISOString()
      : new Date().toISOString();
    const senderId = event.sender_id || 'unknown';

    // Report chat metadata
    this.opts.onChatMetadata(
      chatJid,
      timestamp,
      undefined,
      'feishu',
      event.chat_type === 'group',
    );

    // Handle file/image messages: download and deliver as text reference
    if (
      event.message_type &&
      (event.message_type === 'image' || event.message_type === 'file')
    ) {
      this.handleFileMessage(event, chatJid, messageId, timestamp, senderId);
      return;
    }

    // Skip other non-text types (audio, video, sticker, etc.)
    if (event.message_type && event.message_type !== 'text') {
      logger.debug(
        { messageType: event.message_type },
        'Feishu: skipping unsupported message type',
      );
      return;
    }

    // Deliver text message
    this.opts.onMessage(chatJid, {
      id: messageId,
      chat_jid: chatJid,
      sender: senderId,
      sender_name: senderId,
      content: event.content,
      timestamp,
      is_from_me: false,
    });

    logger.info(
      { chatJid, sender: senderId, messageId },
      'Feishu message received',
    );
  }

  private handleFileMessage(
    event: FeishuEvent,
    chatJid: string,
    messageId: string,
    timestamp: string,
    senderId: string,
  ): void {
    // Parse content to get file_key / image_key.
    // lark-cli --compact rewrites JSON content into human-readable text:
    //   image: "[Image: img_v3_xxx]"
    //   file:  "[File: file_v3_xxx (filename.pdf)]" or raw JSON
    const isImage = event.message_type === 'image';
    const content = event.content || '';
    let fileKey = '';
    let fileName = '';

    // Try compact text format first
    const imageMatch = content.match(/^\[Image:\s*(img_[^\]]+)\]$/);
    const fileMatch = content.match(
      /^\[File:\s*(file_[^\s\]]+)(?:\s*\(([^)]+)\))?\]$/,
    );
    if (isImage && imageMatch) {
      fileKey = imageMatch[1];
      fileName = fileKey;
    } else if (!isImage && fileMatch) {
      fileKey = fileMatch[1];
      fileName = fileMatch[2] || fileKey;
    } else {
      // Fallback: try JSON parse (raw event without --compact)
      try {
        const contentObj: Record<string, string> = JSON.parse(content);
        fileKey = isImage ? contentObj.image_key : contentObj.file_key;
        fileName = contentObj.file_name || fileKey || 'unknown';
      } catch {
        logger.warn(
          { content },
          'Feishu: failed to parse file message content',
        );
        return;
      }
    }

    if (!fileKey) {
      logger.warn({ event }, 'Feishu: file message missing key');
      return;
    }

    // Find the group folder for this chat
    const groups = this.opts.registeredGroups();
    const group = groups[chatJid];
    if (!group) {
      logger.debug(
        { chatJid },
        'Feishu: file from unregistered chat, skipping download',
      );
      return;
    }

    const uploadsDir = path.join(GROUPS_DIR, group.folder, 'uploads');
    fs.mkdirSync(uploadsDir, { recursive: true });

    // lark-cli requires relative output paths — use cwd in uploadsDir.
    // Omit --output so lark-cli infers filename + extension from server headers.
    const downloadArgs = [
      'im',
      '+messages-resources-download',
      '--as',
      'bot',
      ...profileArgs(),
      '--message-id',
      messageId,
      '--file-key',
      fileKey,
      '--type',
      isImage ? 'image' : 'file',
    ];

    const child = spawn('lark-cli', downloadArgs, {
      cwd: uploadsDir,
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: 60000,
    });

    let stdout = '';
    let stderr = '';
    child.stdout?.on('data', (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr?.on('data', (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    child.on('close', (code) => {
      if (code !== 0) {
        logger.error(
          { messageId, fileKey, code, stderr },
          'Feishu: file download failed',
        );
        // Still deliver a message so the agent knows a file was sent
        this.opts.onMessage(chatJid, {
          id: messageId,
          chat_jid: chatJid,
          sender: senderId,
          sender_name: senderId,
          content: `[用户发送了${isImage ? '图片' : '文件'}: ${fileName}，下载失败]`,
          timestamp,
          is_from_me: false,
        });
        return;
      }

      // Parse saved path from lark-cli JSON output
      let savedName = fileName;
      try {
        const result = JSON.parse(stdout);
        if (result.data?.saved_path) {
          savedName = path.basename(result.data.saved_path);
        }
      } catch {
        // Fall back to original fileName
      }

      logger.info(
        { chatJid, messageId, fileKey, savedName },
        'Feishu: file downloaded',
      );

      this.opts.onMessage(chatJid, {
        id: messageId,
        chat_jid: chatJid,
        sender: senderId,
        sender_name: senderId,
        content: `[用户发送了${isImage ? '图片' : '文件'}: uploads/${savedName}]`,
        timestamp,
        is_from_me: false,
      });
    });

    child.on('error', (err) => {
      logger.error(
        { messageId, fileKey, err },
        'Feishu: file download spawn error',
      );
    });
  }
}

registerChannel('feishu', (opts: ChannelOpts) => {
  try {
    execSync('which lark-cli', { stdio: 'ignore', timeout: 5000 });
  } catch {
    logger.warn(
      'Feishu: lark-cli not found. Install with: npm install -g @larksuite/cli',
    );
    return null;
  }
  return new FeishuChannel(opts);
});
