param(
    [Parameter(Mandatory = $true)]
    [string]$MediaRoot,

    [Parameter(Mandatory = $true)]
    [string]$Script,

    [string]$Voice = "",
    [string]$Config = "script_mixer.local.json",
    [string]$DraftRoot = "",
    [string]$ProjectId = "",
    [int]$CandidateCount = 3,
    [double]$HandleBefore = 1.0,
    [double]$HandleAfter = 1.0,
    [switch]$FastScan,
    [switch]$SkipModels,
    [switch]$SkipSourceTranscripts,
    [switch]$NoDraft,
    [switch]$RequireDraft,
    [switch]$NoPreview,
    [switch]$BurnSubtitles
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Test-Path $Config)) {
    throw "Local config not found: $Config. Run scripts/setup_jianying_windows.ps1 first."
}
if (-not (Test-Path $MediaRoot)) {
    throw "Media root not found: $MediaRoot"
}
if (-not (Test-Path $Script)) {
    throw "Script file not found: $Script"
}
if ($Voice -and -not (Test-Path $Voice)) {
    throw "Voice file not found: $Voice"
}

Write-Host "[1/5] Scanning the complete source library..."
$ScanArguments = @("--config", $Config, "scan-media", "--root", $MediaRoot)
if ($FastScan) {
    $ScanArguments += "--fast"
}
& script-driven-mixer @ScanArguments
if ($LASTEXITCODE -ne 0) {
    throw "Media scan failed with exit code $LASTEXITCODE"
}

if (-not $SkipModels) {
    Write-Host "[2/5] Running multi-frame material intelligence and hard packaging filters..."
    & material-intelligence --config $Config analyze
    if ($LASTEXITCODE -ne 0) {
        throw "Material intelligence failed or rejected unanalyzed clips. Review the report before editing."
    }

    if (-not $SkipSourceTranscripts) {
        Write-Host "[3/5] Transcribing dialogue from original source videos..."
        & source-transcripts --config $Config build
        if ($LASTEXITCODE -ne 0) {
            throw "Source transcription failed. Install or configure Whisper, or use -SkipSourceTranscripts explicitly."
        }
    } else {
        Write-Host "[3/5] Source dialogue transcription skipped by explicit request."
    }

    Write-Host "[4/5] Building semantic embeddings from the filtered multimodal catalog..."
    & script-driven-mixer --config $Config build-embeddings
    if ($LASTEXITCODE -ne 0) {
        throw "Embedding build failed with exit code $LASTEXITCODE"
    }
} else {
    Write-Host "[2/5] Material intelligence skipped by explicit request."
    Write-Host "[3/5] Source dialogue transcription skipped by explicit request."
    Write-Host "[4/5] Embedding build skipped by explicit request."
}

$Arguments = @(
    "--config", $Config,
    "make-jianying-project",
    "--script", $Script,
    "--candidate-count", "$CandidateCount",
    "--handle-before", "$HandleBefore",
    "--handle-after", "$HandleAfter",
    "--skip-enrich",
    "--skip-embeddings"
)

if ($Voice) {
    $Arguments += @("--voice", $Voice, "--audio-mode", "mixed")
} else {
    $Arguments += @("--audio-mode", "source")
}
if ($DraftRoot) {
    $Arguments += @("--draft-root", $DraftRoot)
}
if ($ProjectId) {
    $Arguments += @("--project-id", $ProjectId)
}
if ($NoDraft) {
    $Arguments += "--no-draft"
}
if ($RequireDraft) {
    $Arguments += "--require-draft"
}
if ($NoPreview) {
    $Arguments += "--no-preview"
}
if ($BurnSubtitles) {
    $Arguments += "--burn-subtitles"
}

Write-Host "[5/5] Planning the filtered timeline and exporting Jianying editable output..."
& script-driven-mixer @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "Jianying project generation failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Completed. Check outputs/script_mixer/<project_id>/exports/jianying_package"
