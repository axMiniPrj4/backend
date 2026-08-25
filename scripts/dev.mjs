import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const isWin = process.platform === 'win32'
const venvPython = path.join(root, '.venv', isWin ? 'Scripts/python.exe' : 'bin/python')
const python = existsSync(venvPython) ? venvPython : (isWin ? 'python' : 'python3')

const child = spawn(
  python,
  ['-m', 'uvicorn', 'app.main:app', '--reload', '--port', '8001'],
  {
    cwd: root,
    stdio: 'inherit',
    shell: false,
    env: process.env,
  },
)

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal)
  process.exit(code ?? 1)
})
