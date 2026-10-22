"""Download the small SQLite NuGet dependency set when dotnet restore has no direct network."""
import pathlib
import sys
import urllib.request

packages = {
    'microsoft.data.sqlite': '10.0.2',
    'microsoft.data.sqlite.core': '10.0.2',
    'sqlitepclraw.bundle_e_sqlite3': '2.1.11',
    'sqlitepclraw.core': '2.1.11',
    'sqlitepclraw.provider.e_sqlite3': '2.1.11',
    'sqlitepclraw.lib.e_sqlite3': '2.1.11',
}
target = pathlib.Path(sys.argv[1])
target.mkdir(parents=True, exist_ok=True)
for name, version in packages.items():
    output = target / f'{name}.{version}.nupkg'
    if output.exists():
        continue
    url = f'https://api.nuget.org/v3-flatcontainer/{name}/{version}/{name}.{version}.nupkg'
    urllib.request.urlretrieve(url, output)
    print(f'Downloaded {output.name}')
