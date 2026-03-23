#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Logitech Unifying Receiver Driver Reset Tool
    Removes cached driver state for MI_02 (HID++ interface) and forces
    Windows to re-enumerate the receiver from scratch.

    Must be run as Administrator.

.USAGE
    Right-click PowerShell → Run as Administrator
    Then: .\fix_receiver.ps1
#>

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Logitech Receiver Driver Reset Tool" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[ERROR] This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell → Run as Administrator" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[1/5] Scanning for Logitech Unifying receiver devices..." -ForegroundColor Yellow

# Find all Logitech PnP devices related to the Unifying receiver
$logiDevices = Get-PnpDevice -FriendlyName "*Logitech*" -ErrorAction SilentlyContinue
$receiverDevices = Get-PnpDevice | Where-Object {
    $_.InstanceId -like "*VID_046D&PID_C52B*"
} -ErrorAction SilentlyContinue

if (-not $receiverDevices) {
    Write-Host "[ERROR] No Logitech Unifying receiver (PID=C52B) found!" -ForegroundColor Red
    Write-Host "Is the receiver plugged in?" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "Found devices:" -ForegroundColor Green
$receiverDevices | ForEach-Object {
    $status = if ($_.Status -eq "OK") { "OK" } else { "ERROR" }
    $color = if ($_.Status -eq "OK") { "Green" } else { "Red" }
    Write-Host ("  [{0}] {1}" -f $status, $_.InstanceId) -ForegroundColor $color
    Write-Host ("        {0}" -f $_.FriendlyName)
}

# Find error devices
$errorDevices = $receiverDevices | Where-Object { $_.Status -ne "OK" }
$allDevices = $receiverDevices

Write-Host ""
if ($errorDevices) {
    Write-Host "[!] Found $($errorDevices.Count) device(s) in Error state" -ForegroundColor Red
} else {
    Write-Host "[i] No error devices found, but will reset anyway" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[2/5] UNPLUG THE RECEIVER NOW and press Enter..." -ForegroundColor Yellow -NoNewline
Read-Host

Write-Host ""
Write-Host "[3/5] Removing all Logitech receiver device entries..." -ForegroundColor Yellow

$removed = 0
foreach ($dev in $allDevices) {
    try {
        Write-Host "  Removing: $($dev.InstanceId)..." -NoNewline
        # Disable first if enabled
        if ($dev.Status -eq "OK") {
            Disable-PnpDevice -InstanceId $dev.InstanceId -Confirm:$false -ErrorAction SilentlyContinue
        }
        # Remove the device node
        $result = pnputil /remove-device $dev.InstanceId 2>&1
        if ($LASTEXITCODE -eq 0 -or $result -match "success") {
            Write-Host " OK" -ForegroundColor Green
            $removed++
        } else {
            # Try alternative removal
            $dev | Remove-PnpDevice -Confirm:$false -ErrorAction SilentlyContinue
            Write-Host " OK (alt)" -ForegroundColor Green
            $removed++
        }
    } catch {
        Write-Host " SKIP ($($_.Exception.Message))" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "  Removed $removed device(s)" -ForegroundColor Green

# Also clean up any ghost Logitech Cordless Device entries
Write-Host ""
Write-Host "[4/5] Cleaning up ghost 'Logitech Cordless Device' entries..." -ForegroundColor Yellow

$ghostDevices = Get-PnpDevice -FriendlyName "*Logitech Cordless*" -ErrorAction SilentlyContinue
if ($ghostDevices) {
    foreach ($ghost in $ghostDevices) {
        try {
            Write-Host "  Removing ghost: $($ghost.FriendlyName)..." -NoNewline
            pnputil /remove-device $ghost.InstanceId 2>&1 | Out-Null
            Write-Host " OK" -ForegroundColor Green
        } catch {
            Write-Host " SKIP" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "  No ghost devices found" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "[5/5] PLUG THE RECEIVER BACK IN NOW" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Windows will re-detect and install drivers from scratch." -ForegroundColor White
Write-Host "Wait 10-15 seconds for the mouse to reconnect, then run hid_debug.exe" -ForegroundColor White
Write-Host "to verify the 0xFF00 interfaces appear." -ForegroundColor White
Write-Host ""
Read-Host "Press Enter to exit"
