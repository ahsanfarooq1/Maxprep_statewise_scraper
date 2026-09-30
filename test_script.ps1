$statesInput = "OR:Oregon_scraped_data"
if ([string]::IsNullOrWhiteSpace($statesInput)) {
  $statesInput = "AZ:Arizona_Scraped_data AR:Arkansas_scraped_data CO:Colorado_Scraped_data ID:Idaho_scraped_data IN:Indiana_scraped_data KY:Kentucky_Scraped_data LA:Louisiana_scraped_data MI:Michigan_scraped_data NV:Nevada_Scraped_data NM:NewMaxico_scraped_data OH:Ohio_scraped_data OK:Oklahoma_scraped_data OR:Oregon_scraped_data TX:Texas_scraped_data UT:Utah_Scraped_data WA:Washington_scraped_data WI:Wisconsin_scraped_data"
}
$sportsInput = "boys"
if ([string]::IsNullOrWhiteSpace($sportsInput)) {
  $sportsInput = "boys girls"
}
$force = "false" -eq 'true'

$entries = $statesInput -split '\s+' | Where-Object { $_ -ne '' }
$sports  = $sportsInput -split '\s+' | Where-Object { $_ -ne '' }

$codeDir = Join-Path $env:GITHUB_WORKSPACE "code"
$dataDir = Join-Path $env:GITHUB_WORKSPACE "data"
$today   = [DateTime]::UtcNow.ToString('yyyy-MM-dd')

# 30 min per state/sport. If MaxPreps or the network hangs on one
# state, this is what stops it from burning the entire window -
# kill it and move on, the skip-check below will retry it at the
# next check-in instead of blocking everything after it today.
$maxMs = 30 * 60 * 1000

Set-Location $dataDir
git config user.name "maxpreps-daily-bot"
git config user.email "actions@users.noreply.github.com"

$done = 0
$skipped = 0
$failed = 0

foreach ($entry in $entries) {
  $parts  = $entry -split ':', 2
  $code   = $parts[0]
  $folder = $parts[1]
  $outDir = Join-Path $dataDir $folder
  New-Item -ItemType Directory -Force -Path $outDir | Out-Null

  foreach ($sport in $sports) {
    $gapsFile = Join-Path $outDir "$($code.ToLower())_data_gaps_${sport}_2026_2027.json"

    $skip = $false
    if (-not $force -and (Test-Path $gapsFile)) {
      try {
        $meta = (Get-Content $gapsFile -Raw | ConvertFrom-Json).meta
        if ($meta.last_updated -and $meta.last_updated.StartsWith($today)) {
          $skip = $true
        }
      } catch {
        # Unreadable/partial file from an earlier interrupted run -
        # do NOT trust it as "done today", re-run it for real.
        $skip = $false
      }
    }

    if ($skip) {
      Write-Output "::group::$code ($sport) - already refreshed today, skipping"
      Write-Output "::endgroup::"
      $skipped++
      continue
    }

    Write-Output "::group::$code ($sport)"
    Set-Location $codeDir
    $proc = Start-Process -FilePath "py" -ArgumentList @(
      "APP/pipeline.py", "--state", $code, "--sport", $sport,
      "--season", $env:SEASON, "--output-dir", $outDir, "--workers", "15"
    ) -NoNewWindow -PassThru
    $finished = $proc.WaitForExit($maxMs)
    if (-not $finished) {
      Write-Output "[WARN] $code $sport exceeded $($maxMs/60000) min - killing, will retry at the next check-in"
      try { $proc.Kill() } catch {}
      $failed++
    } elseif ($proc.ExitCode -ne 0) {
      Write-Output "[WARN] $code $sport pipeline exited $($proc.ExitCode) - will retry at the next check-in"
      $failed++
    } else {
      $done++
    }
    Write-Output "::endgroup::"

    # Commit + push THIS state/sport's result right now, whatever
    # it is - a partial/killed run's OWN files may still have
    # earlier stages' output worth keeping, and a later failure
    # elsewhere must never take this progress down with it.
    Set-Location $dataDir
    git add -A
    git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
      $stamp = [DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm')
      git commit -m "Scrape: $code $sport - $stamp UTC" | Out-Null
      git push origin data
    }
  }
}

Write-Output "Done: $done  Skipped (already fresh today): $skipped  Failed/timed out: $failed"
exit 0
