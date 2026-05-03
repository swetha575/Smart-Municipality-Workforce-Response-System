[CmdletBinding()]
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 5000,
    [switch]$SkipBrowser,
    [switch]$InstallOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"
$FaceModelPath = Join-Path $ProjectRoot "app\onnx_model\face_model.onnx"
$RuntimeUrl = "http://{0}:{1}/login" -f $BindHost, $Port
$SupportedPythonVersions = @("3.11", "3.12")

function Write-Status {
    param([string]$Message)

    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Refresh-SessionPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $combined = @($machinePath, $userPath) | Where-Object { $_ -and $_.Trim() }
    $env:Path = ($combined -join ";")
}

function Get-PythonExecutable {
    $candidates = @(
        @{ Command = "py"; Args = @("-3.11", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}|{sys.executable}')") },
        @{ Command = "py"; Args = @("-3.12", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}|{sys.executable}')") },
        @{ Command = "python"; Args = @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}|{sys.executable}')") }
    )

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) {
            continue
        }

        try {
            $output = & $candidate.Command @($candidate.Args) 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $output) {
                continue
            }

            $versionedPath = ($output | Select-Object -Last 1).ToString().Trim()
            $parts = $versionedPath -split "\|", 2
            if ($parts.Count -ne 2) {
                continue
            }

            $version = $parts[0].Trim()
            $resolved = $parts[1].Trim()
            if (($SupportedPythonVersions -contains $version) -and $resolved -and (Test-Path $resolved)) {
                return (Resolve-Path $resolved).Path
            }
        } catch {
        }
    }

    $knownPaths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
        "C:\Program Files\Python311\python.exe",
        "C:\Python311\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Python312\python.exe"
    )

    foreach ($path in $knownPaths) {
        if (Test-Path $path) {
            return (Resolve-Path $path).Path
        }
    }

    return $null
}

function Get-PythonVersion {
    param([string]$PythonPath)

    if (-not (Test-Path $PythonPath)) {
        return $null
    }

    try {
        $version = & $PythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $version) {
            return ($version | Select-Object -Last 1).ToString().Trim()
        }
    } catch {
    }

    return $null
}

function Install-PythonIfMissing {
    $pythonExe = Get-PythonExecutable
    if ($pythonExe) {
        return $pythonExe
    }

    Write-Status "Python was not found. Installing Python 3.11 automatically."

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        & winget install --id Python.Python.3.11 --exact --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            throw "winget could not install Python 3.11."
        }
        Refresh-SessionPath
    } else {
        $installerUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
        $installerPath = Join-Path $env:TEMP "python-3.11.9-amd64.exe"

        Write-Status "Downloading Python installer from python.org."
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath

        Write-Status "Running the Python installer silently."
        $installerArgs = @(
            "/quiet",
            "InstallAllUsers=0",
            "PrependPath=1",
            "Include_test=0",
            "SimpleInstall=1",
            "Include_launcher=1"
        )
        $process = Start-Process -FilePath $installerPath -ArgumentList $installerArgs -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            throw "Python installer exited with code $($process.ExitCode)."
        }
        Refresh-SessionPath
    }

    $pythonExe = Get-PythonExecutable
    if (-not $pythonExe) {
        throw "Python installation finished, but python.exe could not be located."
    }

    return $pythonExe
}

function Ensure-Directory {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
}

Set-Location $ProjectRoot

if (-not (Test-Path $RequirementsFile)) {
    throw "requirements.txt was not found in $ProjectRoot."
}

if (-not (Test-Path $FaceModelPath)) {
    throw "Required face model file is missing: $FaceModelPath"
}

$PythonExe = Install-PythonIfMissing
Write-Status "Using Python at $PythonExe"

if (Test-Path $VenvPython) {
    $venvVersion = Get-PythonVersion -PythonPath $VenvPython
    if ($SupportedPythonVersions -notcontains $venvVersion) {
        Write-Status "Rebuilding the local virtual environment because it uses unsupported Python $venvVersion."
        Remove-Item -LiteralPath $VenvDir -Recurse -Force
    }
}

if (-not (Test-Path $VenvPython)) {
    Write-Status "Creating the virtual environment."
    & $PythonExe -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        throw "Virtual environment creation failed."
    }
}

$requiredFolders = @(
    (Join-Path $ProjectRoot "instance"),
    (Join-Path $ProjectRoot "app\static\uploads"),
    (Join-Path $ProjectRoot "app\static\uploads\task_before"),
    (Join-Path $ProjectRoot "app\static\uploads\task_after"),
    (Join-Path $ProjectRoot "app\static\uploads\complaint_images"),
    (Join-Path $ProjectRoot "app\static\uploads\complaint_voice")
)

foreach ($folder in $requiredFolders) {
    Ensure-Directory -Path $folder
}

Write-Status "Upgrading pip tooling."
& $VenvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
    throw "pip tooling upgrade failed."
}

Write-Status "Installing project dependencies."
& $VenvPython -m pip install -r $RequirementsFile
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

$env:SECRET_KEY = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
$env:SESSION_COOKIE_SECURE = "0"
$env:APP_HOST = $BindHost
$env:APP_PORT = $Port.ToString()
$env:APP_DEBUG = "0"

Write-Status "Verifying imports and initializing the database."
& $VenvPython -c "import cv2, flask, numpy, onnxruntime; from app import create_app; app = create_app(); print('BOOTSTRAP_OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Application bootstrap verification failed."
}

if ($InstallOnly) {
    Write-Status "Install-only run completed. Start the app later with start_client_app.bat."
    exit 0
}

if (-not $SkipBrowser) {
    Start-Job -ScriptBlock {
        param([string]$Url)

        Start-Sleep -Seconds 4
        Start-Process $Url
    } -ArgumentList $RuntimeUrl | Out-Null
}

Write-Status "Starting the Smart Municipal application at $RuntimeUrl"
Write-Status "Default admin login: admin@example.com / Admin@123"
& $VenvPython "$ProjectRoot\run.py"
