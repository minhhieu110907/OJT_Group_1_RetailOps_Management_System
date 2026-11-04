$ErrorActionPreference = "Stop"

$projectName = "retailops-migration-$([guid]::NewGuid().ToString('N').Substring(0, 12))"
$volumeName = "${projectName}_mysql_data"
$secretSuffix = [guid]::NewGuid().ToString("N")

$env:MYSQL_DATABASE = "retailops_migration_check"
$env:MYSQL_TEST_DATABASE = "retailops_migration_check_test"
$env:MYSQL_USER = "retailops_migration_app"
$env:MYSQL_PASSWORD = "app_${secretSuffix}"
$env:MYSQL_TEST_USER = "retailops_migration_test"
$env:MYSQL_TEST_PASSWORD = "test_${secretSuffix}"
$env:MYSQL_ROOT_PASSWORD = "root_${secretSuffix}"
$env:MYSQL_HOST_PORT = "0"
$env:BACKEND_HOST_PORT = "0"

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
    Invoke-DockerCompose run --rm backend alembic current

    $tables = & docker compose --project-name $projectName exec --no-TTY `
        --env "MYSQL_PWD=$($env:MYSQL_PASSWORD)" mysql mysql `
        --batch --skip-column-names --user=$env:MYSQL_USER `
        $env:MYSQL_DATABASE `
        --execute="SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() ORDER BY table_name"
    if ($LASTEXITCODE -ne 0 -or ($tables -join ",") -ne "alembic_version") {
        throw "Fresh migration database contains unexpected tables"
    }
}
finally {
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
