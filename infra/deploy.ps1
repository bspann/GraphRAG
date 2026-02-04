# =============================================================================
# Azure Government App Service Deployment Script
# PowerShell script for deploying the Flask RAG application
# =============================================================================

param(
    [Parameter(Mandatory=$true)]
    [string]$AppServiceName,
    
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroupName,
    
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

Write-Host "🚀 Deploying Flask RAG Application to Azure Government" -ForegroundColor Cyan
Write-Host "   App Service: $AppServiceName" -ForegroundColor Gray
Write-Host "   Resource Group: $ResourceGroupName" -ForegroundColor Gray

# Verify Azure CLI is configured for Azure Government
$cloud = az cloud show --query name -o tsv
if ($cloud -ne "AzureUSGovernment") {
    Write-Host "⚠️  Setting Azure CLI to Azure Government cloud..." -ForegroundColor Yellow
    az cloud set --name AzureUSGovernment
    az login
}

# Get the script directory (infra folder)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appDir = Split-Path -Parent $scriptDir

Write-Host "`n📁 Application directory: $appDir" -ForegroundColor Gray

# Create deployment package
Write-Host "`n📦 Creating deployment package..." -ForegroundColor Cyan

$tempDir = Join-Path $env:TEMP "flask-rag-deploy-$(Get-Date -Format 'yyyyMMddHHmmss')"
$zipPath = Join-Path $env:TEMP "flask-rag-app.zip"

# Create temp directory
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

# Copy application files
$excludePatterns = @(
    ".venv",
    "__pycache__",
    ".git",
    ".env",
    "*.pyc",
    ".pytest_cache",
    "infra",
    ".terraform"
)

Get-ChildItem -Path $appDir -Recurse | Where-Object {
    $path = $_.FullName
    $exclude = $false
    foreach ($pattern in $excludePatterns) {
        if ($path -like "*$pattern*") {
            $exclude = $true
            break
        }
    }
    -not $exclude
} | ForEach-Object {
    $relativePath = $_.FullName.Substring($appDir.Length + 1)
    $targetPath = Join-Path $tempDir $relativePath
    
    if ($_.PSIsContainer) {
        New-Item -ItemType Directory -Path $targetPath -Force | Out-Null
    } else {
        $targetDir = Split-Path -Parent $targetPath
        if (-not (Test-Path $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }
        Copy-Item -Path $_.FullName -Destination $targetPath -Force
    }
}

# Create startup command file
$startupCommand = @"
gunicorn --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 120 run:app
"@
$startupCommand | Out-File -FilePath (Join-Path $tempDir "startup.txt") -Encoding UTF8

# Create zip package
Write-Host "   Compressing files..." -ForegroundColor Gray
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
Compress-Archive -Path "$tempDir\*" -DestinationPath $zipPath -Force

Write-Host "   Package created: $zipPath" -ForegroundColor Green

# Deploy to App Service
Write-Host "`n🚢 Deploying to App Service..." -ForegroundColor Cyan

az webapp deploy `
    --resource-group $ResourceGroupName `
    --name $AppServiceName `
    --src-path $zipPath `
    --type zip `
    --async false

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Deployment successful!" -ForegroundColor Green
    
    # Get the app URL
    $appUrl = az webapp show `
        --resource-group $ResourceGroupName `
        --name $AppServiceName `
        --query "defaultHostName" -o tsv
    
    Write-Host "`n🌐 Application URL: https://$appUrl" -ForegroundColor Cyan
    Write-Host "🔍 Health check: https://$appUrl/health" -ForegroundColor Gray
} else {
    Write-Host "`n❌ Deployment failed!" -ForegroundColor Red
    exit 1
}

# Cleanup
Write-Host "`n🧹 Cleaning up temporary files..." -ForegroundColor Gray
Remove-Item -Path $tempDir -Recurse -Force
Remove-Item -Path $zipPath -Force

Write-Host "`n✨ Done!" -ForegroundColor Green
