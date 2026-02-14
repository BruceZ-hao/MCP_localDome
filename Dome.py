#!/usr/bin/env python3
"""
ESP32S3 + QwQ-32B AI控制器 v3.1
修复版 - 解决UI显示问题
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import requests
import json
import threading
import serial
import serial.tools.list_ports
import time
import re


class AIClient:
    """AI客户端"""
    
    API_URL = "http://127.0.0.1:8000/chat"
    
    SYSTEM_PROMPT = '''你是一个智能助手，可以控制ESP32S3开发板。

可用控制命令：
- 开灯: <MCP>{"action":"gpio","pin":2,"value":1}</MCP>
- 关灯: <MCP>{"action":"gpio","pin":2,"value":0}</MCP>
- PWM: <MCP>{"action":"pwm","pin":4,"duty":500}</MCP>

规则：用户要求控制硬件时，立即输出MCP命令，然后回复用户。'''
    
    def __init__(self):
        self.session_messages = []
        self.max_history = 4
        self.connected = False
        
    def test_connection(self):
        """测试连接"""
        try:
            r = requests.get("http://127.0.0.1:8000/health", timeout=2)
            self.connected = r.status_code == 200
            return self.connected
        except:
            self.connected = False
            return False
    
    def chat(self, message):
        """发送消息"""
        if not self.test_connection():
            raise Exception("API未连接，请检查: python api.py")
        
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            *self.session_messages[-self.max_history*2:],
            {"role": "user", "content": message}
        ]
        
        try:
            response = requests.post(
                self.API_URL,
                json={"messages": messages, "stream": False},
                timeout=60,
                headers={
                    "Content-Type": "application/json",
                    "Connection": "close"
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"HTTP错误: {response.status_code}")
            
            result = response.json()
            content = result.get("content", "")
            
            if not content:
                raise Exception("AI返回空内容")
            
            # 保存历史
            self.session_messages.append({"role": "user", "content": message})
            self.session_messages.append({"role": "assistant", "content": content})
            
            # 限制长度
            if len(self.session_messages) > self.max_history * 2:
                self.session_messages = self.session_messages[-self.max_history * 2:]
            
            self.connected = True
            return content
            
        except requests.exceptions.Timeout:
            self.connected = False
            raise Exception("请求超时，请重试")
        except Exception as e:
            self.connected = False
            raise Exception(f"请求失败: {str(e)}")
    
    def clear_history(self):
        self.session_messages = []


class MCPProtocol:
    @staticmethod
    def extract_commands(text):
        pattern = r'<MCP>(.*?)</MCP>'
        matches = re.findall(pattern, text, re.DOTALL)
        commands = []
        for match in matches:
            try:
                commands.append(json.loads(match))
            except:
                pass
        return commands


class ESP32Controller:
    def __init__(self):
        self.serial = None
        self.connected = False
        self._lock = threading.Lock()
        
    def connect(self, port, baudrate=115200):
        try:
            self.serial = serial.Serial(port, baudrate, timeout=2)
            time.sleep(2)
            self.serial.reset_input_buffer()
            self.connected = True
            return True, "OK"
        except Exception as e:
            return False, str(e)
    
    def disconnect(self):
        with self._lock:
            if self.serial and self.serial.is_open:
                self.serial.close()
            self.connected = False
    
    def send_command(self, cmd_dict):
        if not self.is_connected():
            return False, "未连接"
        
        try:
            with self._lock:
                char = self._to_char(cmd_dict)
                if char:
                    self.serial.write(char.encode())
                    self.serial.flush()
                    return True, f"发送'{char.strip()}'"
            return False, "未知命令"
        except Exception as e:
            return False, str(e)
    
    def _to_char(self, cmd):
        a, p, v = cmd.get("action"), cmd.get("pin"), cmd.get("value", 0)
        d = cmd.get("duty", 0)
        
        if a == "gpio":
            if p == 2 and v == 1: return 'A'
            if p == 2 and v == 0: return 'a'
        if a == "pwm" and p == 4:
            return f"P{d:04d}\n"
        return None
    
    def send_pwm(self, duty):
        if not self.is_connected():
            return
        with self._lock:
            try:
                self.serial.write(f"P{duty:04d}\n".encode())
                self.serial.flush()
            except:
                pass
    
    def get_ports(self):
        try:
            return [p.device for p in serial.tools.list_ports.comports()]
        except:
            return []
    
    def is_connected(self):
        return self.connected and self.serial and self.serial.is_open


class MainGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🤖 ESP32S3 + AI控制器 v3.1")
        self.root.geometry("1000x700")
        self.root.configure(bg='#0d1117')
        
        self.ai = AIClient()
        self.esp32 = ESP32Controller()
        self.mcp = MCPProtocol()
        
        self._create_ui()
        self._check_status()
        
    def _create_ui(self):
        # 顶部状态栏
        header = tk.Frame(self.root, bg='#161b22', height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        self.ai_status = tk.Label(header, text="🟡 检查中...", 
                                   bg='#161b22', fg='#f39c12',
                                   font=('微软雅黑', 11))
        self.ai_status.pack(side=tk.LEFT, padx=20, pady=10)
        
        tk.Label(header, text="串口:", bg='#161b22', fg='white').pack(side=tk.LEFT)
        self.port_combo = ttk.Combobox(header, width=12)
        self.port_combo.pack(side=tk.LEFT, padx=5)
        
        tk.Button(header, text="连接", command=self._toggle_esp32,
                  bg='#e84545', fg='white').pack(side=tk.LEFT, padx=5)
        
        self.esp_status = tk.Label(header, text="● 未连接", 
                                   bg='#161b22', fg='#e84545')
        self.esp_status.pack(side=tk.LEFT, padx=10)
        
        tk.Button(header, text="🗑️ 清除历史", command=self._clear_history,
                  bg='#21262d', fg='white').pack(side=tk.RIGHT, padx=20)
        
        # 主区域
        content = tk.Frame(self.root, bg='#0d1117')
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 左侧聊天
        left = tk.Frame(content, bg='#0d1117')
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        chat_frame = tk.LabelFrame(left, text=" AI对话 ", bg='#0d1117', fg='white')
        chat_frame.pack(fill=tk.BOTH, expand=True)
        
        self.chat_box = scrolledtext.ScrolledText(
            chat_frame, bg='#161b22', fg='#c9d1d9',
            font=('Consolas', 11), state=tk.DISABLED
        )
        self.chat_box.pack(fill=tk.BOTH, expand=True)
        self.chat_box.tag_config("user", foreground='#7ee787')
        self.chat_box.tag_config("ai", foreground='#79c0ff')
        self.chat_box.tag_config("mcp", foreground='#ff7b72', background='#3d1619')
        self.chat_box.tag_config("error", foreground='#f85149')
        
        # 输入
        input_frame = tk.Frame(left, bg='#0d1117', pady=10)
        input_frame.pack(fill=tk.X)
        
        self.entry = tk.Entry(input_frame, bg='#21262d', fg='white', font=('微软雅黑', 12))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.entry.bind('<Return>', lambda e: self._send())
        
        tk.Button(input_frame, text="发送", command=self._send,
                  bg='#238636', fg='white', font=('微软雅黑', 11)).pack(side=tk.RIGHT)
        
        # 快捷按钮
        quick = tk.Frame(left, bg='#0d1117')
        quick.pack(fill=tk.X, pady=5)
        
        for text, cmd in [("💡开灯", "打开灯"), ("🌑关灯", "关闭灯"), 
                         ("✨闪烁", "让灯闪烁"), ("📊ADC", "读取ADC")]:
            tk.Button(quick, text=text, command=lambda c=cmd: self._quick(c),
                     bg='#21262d', fg='white').pack(side=tk.LEFT, padx=5)
        
        # 右侧控制
        right = tk.Frame(content, bg='#0d1117', width=300)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(20, 0))
        right.pack_propagate(False)
        
        # LED
        led = tk.LabelFrame(right, text=" LED控制 ", bg='#0d1117', fg='white')
        led.pack(fill=tk.X, pady=10)
        
        tk.Button(led, text="ON", command=lambda: self._manual(2, 1),
                  bg='#238636', fg='white', width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(led, text="OFF", command=lambda: self._manual(2, 0),
                  bg='#e84545', fg='white', width=10).pack(side=tk.LEFT, padx=5)
        
        # PWM
        pwm = tk.LabelFrame(right, text=" PWM控制 ", bg='#0d1117', fg='white')
        pwm.pack(fill=tk.X, pady=10)
        
        self.pwm_val = tk.Label(pwm, text="0", bg='#0d1117', fg='#58a6ff', font=('Consolas', 24))
        self.pwm_val.pack()
        
        self.slider = tk.Scale(pwm, from_=0, to=1000, orient=tk.HORIZONTAL,
                              bg='#0d1117', fg='white', highlightthickness=0,
                              command=self._on_pwm)
        self.slider.set(0)
        self.slider.pack(fill=tk.X, padx=10)
        
        # 日志
        log = tk.LabelFrame(right, text=" 日志 ", bg='#0d1117', fg='white')
        log.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.log_box = scrolledtext.ScrolledText(log, bg='#161b22', fg='#3fb950', height=10)
        self.log_box.pack(fill=tk.BOTH, expand=True)
    
    def _check_status(self):
        """定期检查状态"""
        def check():
            if self.ai.test_connection():
                self.ai_status.config(text="🟢 AI正常", fg='#3fb950')
            else:
                self.ai_status.config(text="🔴 AI断开", fg='#f85149')
            
            ports = self.esp32.get_ports()
            self.port_combo['values'] = ports
            if ports and not self.port_combo.get():
                self.port_combo.set(ports[0])
        
        threading.Thread(target=check, daemon=True).start()
        self.root.after(5000, self._check_status)
    
    def _toggle_esp32(self):
        if self.esp32.is_connected():
            self.esp32.disconnect()
            self.esp_status.config(text="● 未连接", fg='#e84545')
            self._log("ESP32断开")
        else:
            port = self.port_combo.get()
            if not port:
                messagebox.showerror("错误", "请选择串口")
                return
            
            ok, msg = self.esp32.connect(port)
            if ok:
                self.esp_status.config(text="● 已连接", fg='#3fb950')
                self._log(f"ESP32连接: {port}")
            else:
                messagebox.showerror("失败", msg)
    
    def _send(self):
        """发送消息 - 修复版"""
        text = self.entry.get().strip()
        if not text:
            return
        
        self.entry.delete(0, tk.END)
        self._add_chat("你", text, "user")
        
        # 显示思考中
        self.chat_box.config(state=tk.NORMAL)
        self.chat_box.insert(tk.END, "AI: 思考中...\n", "ai")
        self.chat_box.see(tk.END)
        self.chat_box.config(state=tk.DISABLED)
        
        def do_send():
            try:
                result = self.ai.chat(text)
                
                # 在主线程更新UI
                self.root.after(0, lambda: self._update_chat(result))
                
                # 执行MCP命令
                cmds = self.mcp.extract_commands(result)
                for cmd in cmds:
                    if self.esp32.is_connected():
                        ok, msg = self.esp32.send_command(cmd)
                        self._log(f"MCP: {cmd} -> {msg}")
                
            except Exception as e:
                self.root.after(0, lambda err=str(e): self._show_error(err))
        
        threading.Thread(target=do_send, daemon=True).start()
    
    def _update_chat(self, text):
        """更新聊天显示 - 关键修复"""
        self.chat_box.config(state=tk.NORMAL)
        
        # 找到并删除"思考中"行
        content = self.chat_box.get('1.0', tk.END)
        lines = content.split('\n')
        
        for i in range(len(lines)-1, -1, -1):
            if "思考中" in lines[i] and lines[i].startswith("AI:"):
                # 删除这一行
                start = f"{i+1}.0"
                end = f"{i+2}.0"
                self.chat_box.delete(start, end)
                break
        
        # 清理文本
        display_text = text.strip()
        
        # 高亮MCP命令
        parts = re.split(r'(<MCP>.*?</MCP>)', display_text)
        
        self.chat_box.insert(tk.END, "AI: ", "ai")
        for part in parts:
            tag = "mcp" if part.startswith('<MCP>') else "ai"
            self.chat_box.insert(tk.END, part, tag)
        
        self.chat_box.insert(tk.END, "\n\n")
        self.chat_box.see(tk.END)
        self.chat_box.config(state=tk.DISABLED)
        
        self._log(f"AI回复: {display_text[:50]}...")
    
    def _show_error(self, msg):
        """显示错误"""
        self.chat_box.config(state=tk.NORMAL)
        
        # 删除思考中
        content = self.chat_box.get('1.0', tk.END)
        lines = content.split('\n')
        for i in range(len(lines)-1, -1, -1):
            if "思考中" in lines[i]:
                self.chat_box.delete(f"{i+1}.0", f"{i+2}.0")
                break
        
        self.chat_box.insert(tk.END, f"错误: {msg}\n\n", "error")
        self.chat_box.see(tk.END)
        self.chat_box.config(state=tk.DISABLED)
        
        self.ai_status.config(text="🔴 AI错误", fg='#f85149')
    
    def _quick(self, cmd):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, cmd)
        self._send()
    
    def _manual(self, pin, val):
        if not self.esp32.is_connected():
            messagebox.showwarning("提示", "请先连接ESP32")
            return
        cmd = {"action": "gpio", "pin": pin, "value": val}
        ok, msg = self.esp32.send_command(cmd)
        self._log(f"手动控制: {msg}")
    
    def _on_pwm(self, val):
        duty = int(val)
        self.pwm_val.config(text=str(duty))
        self.esp32.send_pwm(duty)
    
    def _clear_history(self):
        self.ai.clear_history()
        self._log("历史已清除")
    
    def _add_chat(self, sender, text, tag):
        self.chat_box.config(state=tk.NORMAL)
        self.chat_box.insert(tk.END, f"{sender}: {text}\n", tag)
        self.chat_box.see(tk.END)
        self.chat_box.config(state=tk.DISABLED)
    
    def _log(self, msg):
        from datetime import datetime
        t = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{t}] {msg}\n")
        self.log_box.see(tk.END)


def main():
    print("=" * 50)
    print("ESP32S3 + AI控制器 v3.1")
    print("=" * 50)
    print("1. 启动API: python api.py")
    print("2. 连接ESP32")
    print("3. 开始对话")
    print("=" * 50)
    
    root = tk.Tk()
    app = MainGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()