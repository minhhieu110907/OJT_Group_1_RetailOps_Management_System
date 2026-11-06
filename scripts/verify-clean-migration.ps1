$ErrorActionPreference = "Stop"

$projectName = "retailops-migration-$([guid]::NewGuid().ToString('N').Substring(0, 12))"
$volumeName = "${projectName}_mysql_data"
$secretSuffix = [guid]::NewGuid().ToString("N")
$environmentVariableNames = @(
    "MYSQL_DATABASE",
    "MYSQL_TEST_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_TEST_USER",
    "MYSQL_TEST_PASSWORD",
    "MYSQL_ROOT_PASSWORD",
    "MYSQL_HOST_PORT",
    "BACKEND_HOST_PORT",
    "RETAILOPS_ADMIN_SEED_EMAIL",
    "RETAILOPS_ADMIN_SEED_PASSWORD"
)
$savedEnvironment = @{}

foreach ($name in $environmentVariableNames) {
    $item = Get-Item -Path "Env:$name" -ErrorAction SilentlyContinue
    $savedEnvironment[$name] = [pscustomobject]@{
        Exists = $null -ne $item
        Value = if ($null -ne $item) { $item.Value } else { $null }
    }
}

$env:MYSQL_DATABASE = "retailops_migration_check"
$env:MYSQL_TEST_DATABASE = "retailops_migration_check_test"
$env:MYSQL_USER = "retailops_migration_app"
$env:MYSQL_PASSWORD = "app_${secretSuffix}"
$env:MYSQL_TEST_USER = "retailops_migration_test"
$env:MYSQL_TEST_PASSWORD = "test_${secretSuffix}"
$env:MYSQL_ROOT_PASSWORD = "root_${secretSuffix}"
$env:MYSQL_HOST_PORT = "0"
$env:BACKEND_HOST_PORT = "0"
$env:RETAILOPS_ADMIN_SEED_EMAIL = "admin-migration-check@example.com"
$env:RETAILOPS_ADMIN_SEED_PASSWORD = "Admin_${secretSuffix}"

function Invoke-DockerCompose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    & docker compose --project-name $projectName @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose command failed"
    }
}

try {
    Invoke-DockerCompose build backend
    Invoke-DockerCompose up --detach --wait mysql
    Invoke-DockerCompose run --rm backend alembic upgrade head
    Invoke-DockerCompose run --rm backend alembic current --check-heads
    Invoke-DockerCompose run --rm backend alembic check
    Invoke-DockerCompose run --rm `
        --env RETAILOPS_ADMIN_SEED_EMAIL `
        --env RETAILOPS_ADMIN_SEED_PASSWORD `
        backend python -m app.modules.auth.seed
    Invoke-DockerCompose run --rm `
        --env RETAILOPS_ADMIN_SEED_EMAIL `
        --env RETAILOPS_ADMIN_SEED_PASSWORD `
        backend python -m app.modules.auth.seed

    $registeredTableOutput = Invoke-DockerCompose run --rm backend python -c `
        "from app.db.metadata import metadata; print(','.join(sorted(metadata.tables)))"
    $registeredTables = @(($registeredTableOutput -join "").Split(",") | Where-Object { $_ })
    if ($registeredTables.Count -eq 0) {
        throw "No registered SQLAlchemy tables were found"
    }

    $tables = & docker compose --project-name $projectName exec --no-TTY `
        --env "MYSQL_PWD=$($env:MYSQL_PASSWORD)" mysql mysql `
        --batch --skip-column-names --user=$env:MYSQL_USER `
        $env:MYSQL_DATABASE `
        --execute="SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() ORDER BY table_name"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect the fresh migration schema"
    }
    $actualTables = @($tables | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $requiredTables = @("alembic_version") + $registeredTables
    $missingTables = @($requiredTables | Where-Object { $_ -notin $actualTables })
    if ($missingTables.Count -ne 0) {
        throw "Fresh migration schema is missing registered SQLAlchemy tables"
    }

    $adminCount = & docker compose --project-name $projectName exec --no-TTY `
        --env "MYSQL_PWD=$($env:MYSQL_PASSWORD)" mysql mysql `
        --batch --skip-column-names --user=$env:MYSQL_USER `
        $env:MYSQL_DATABASE `
        --execute="SELECT COUNT(*) FROM users WHERE admin_slot = 1"
    if ($LASTEXITCODE -ne 0 -or ($adminCount -join "") -ne "1") {
        throw "Admin seed did not produce exactly one Admin"
    }
}
finally {
    try {
        $volumeInspection = & docker volume inspect $volumeName 2>$null
        if ($LASTEXITCODE -eq 0) {
            $volumeDetails = $volumeInspection | ConvertFrom-Json
            $volumeProject = $volumeDetails.Labels."com.docker.compose.project"
        }
        if ($null -ne $volumeProject -and $volumeProject -eq $projectName) {
            Invoke-DockerCompose down --volumes
        }
        else {
            Write-Warning "Temporary volume identity was not verified; automatic cleanup skipped"
            Invoke-DockerCompose down
        }
    }
    finally {
        foreach ($name in $environmentVariableNames) {
            $savedValue = $savedEnvironment[$name]
            if ($savedValue.Exists) {
                Set-Item -Path "Env:$name" -Value $savedValue.Value
            }
            else {
                Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
            }
        }
    }
}
