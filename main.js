const { app, BrowserWindow } = require('electron');
const { spawn, spawnSync } = require('child_process');
const path = require('path');
const http = require('http');
const net = require('net');
const packageJson = require('./package.json');

let pyProc = null;
let mainWindow = null;
let apiPort = 8000;
const APP_VERSION = packageJson.version;
let isSoftRestarting = false;

const fs = require('fs');
const { dialog } = require('electron');
let logDir = null;

function safeAppend(fileName, content) {
    try {
        if (!logDir) {
            logDir = path.join(app.getPath('userData'), 'logs');
            fs.mkdirSync(logDir, { recursive: true });
        }
        fs.appendFileSync(path.join(logDir, fileName), content);
    } catch (_) {
        // Never crash the app because of logging.
    }
}

function resolvePythonCommand() {
    const candidates = [
        { cmd: 'python', argsPrefix: [] },
        { cmd: 'python3', argsPrefix: [] },
        { cmd: 'py', argsPrefix: ['-3'] },
    ];

    for (const c of candidates) {
        try {
            const probe = spawnSync(c.cmd, [...c.argsPrefix, '--version'], {
                windowsHide: true,
                shell: false
            });
            if (probe.status === 0) {
                return c;
            }
        } catch (e) {
            continue;
        }
    }
    return null;
}

function findAvailablePort(startPort = 8000, maxChecks = 50) {
    return new Promise((resolve) => {
        const tryPort = (port, attempts) => {
            if (attempts >= maxChecks) {
                resolve(startPort);
                return;
            }
            const server = net.createServer();
            server.unref();
            server.on('error', () => {
                tryPort(port + 1, attempts + 1);
            });
            server.listen(port, '127.0.0.1', () => {
                const freePort = server.address().port;
                server.close(() => resolve(freePort));
            });
        };
        tryPort(startPort, 0);
    });
}

function createPyProc() {
    let script = path.join(__dirname, 'main.py');
    const py = resolvePythonCommand();
    const externalEnvPath = app.isPackaged
        ? path.join(path.dirname(app.getPath('exe')), '.env')
        : path.join(__dirname, '.env');

    if (!py) {
        dialog.showErrorBox(
            'Python Not Found',
            'Python 3 is required. Please install it with "Add to PATH" checked.'
        );
        return;
    }

    safeAppend('py-out.log', `[${APP_VERSION}] Launching: ${py.cmd} with ${script}\n`);

    pyProc = spawn(py.cmd, [...py.argsPrefix, script], {
        cwd: __dirname,
        windowsHide: true,
        shell: false,
        env: {
            ...process.env,
            API_PORT: String(apiPort),
            PYTHONUNBUFFERED: "1",
            APP_ENV_PATH: externalEnvPath
        }
    });

    pyProc.stdout.on('data', (data) => {
        safeAppend('py-out.log', data.toString());
    });

    pyProc.stderr.on('data', (data) => {
        safeAppend('py-error.log', data.toString());
    });

    pyProc.on('error', (err) => {
        dialog.showErrorBox(`Critical ERROR (v${APP_VERSION})`, `Failed to start backend: ${err.message}`);
    });

    pyProc.on('exit', (code) => {
        pyProc = null;
        if (code !== 0 && code !== null) {
            dialog.showErrorBox(
                `Backend Crashed (v${APP_VERSION})`,
                `Python exited with code ${code}. Check logs in ${app.getPath('userData')}\\logs for the backend error.`
            );
        }
    });
}

function exitPyProc() {
    if (pyProc) {
        pyProc.kill();
        pyProc = null;
    }
}

function checkServerReady(cb) {
    const req = http.get(`http://localhost:${apiPort}/health`, (res) => {
        if (res.statusCode === 200) cb();
        else setTimeout(() => checkServerReady(cb), 500);
    });
    req.on('error', () => { setTimeout(() => checkServerReady(cb), 500); });
}

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        title: `Scalper Trading Bot v${APP_VERSION}`,
        webPreferences: {
            nodeIntegration: true
        },
        autoHideMenuBar: true
    });

    mainWindow.loadURL('file://' + path.join(__dirname, 'loading.html'));

    checkServerReady(() => {
        if (mainWindow) {
            mainWindow.loadURL(`http://localhost:${apiPort}`);
        }
    });

    const softRestartWindow = () => {
        if (!mainWindow || isSoftRestarting) return;
        isSoftRestarting = true;
        mainWindow.loadURL('file://' + path.join(__dirname, 'loading.html'));
        checkServerReady(() => {
            if (mainWindow) {
                mainWindow.loadURL(`http://localhost:${apiPort}`);
            }
            isSoftRestarting = false;
        });
    };

    mainWindow.webContents.on('will-navigate', (event, targetUrl) => {
        try {
            const parsed = new URL(targetUrl);
            const isLocalHost = parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1';
            const isApiPort = Number(parsed.port || '80') === Number(apiPort);
            if (isLocalHost && isApiPort && parsed.pathname === '/restart') {
                event.preventDefault();
                softRestartWindow();
            }
        } catch (_) {
            // Ignore malformed URLs and allow default behavior.
        }
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
    app.quit()
} else {
    app.on('second-instance', (event, commandLine, workingDirectory) => {
        if (mainWindow) {
            if (mainWindow.isMinimized()) mainWindow.restore()
            mainWindow.focus()
        }
    })

    app.on('ready', async () => {
        // Force clear cache to show latest UI changes
        const { session } = require('electron');
        await session.defaultSession.clearCache();
        await session.defaultSession.clearStorageData();

        apiPort = await findAvailablePort(8000, 100);
        safeAppend('py-out.log', `Using API port ${apiPort}\n`);
        createPyProc();
        createWindow();
    });

    app.on('will-quit', exitPyProc);

    app.on('window-all-closed', () => {
        if (process.platform !== 'darwin') {
            app.quit();
        }
    });
}
