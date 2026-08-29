param(
  [Parameter(Mandatory=$true)][string]$Spec,
  [Parameter(Mandatory=$true)][string]$OutputDir,
  [string]$Voice = "Microsoft Huihui Desktop",
  [int]$Rate = 2
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$items = Get-Content -LiteralPath $Spec -Raw -Encoding UTF8 | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $synth.SelectVoice($Voice)
  $synth.Rate = $Rate
  foreach ($item in $items) {
    $target = Join-Path $OutputDir ($item.id + ".wav")
    $synth.SetOutputToWaveFile($target)
    $synth.Speak([string]$item.text)
    $synth.SetOutputToNull()
  }
} finally {
  $synth.Dispose()
}
