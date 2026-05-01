# Arcflare OAuth Connector

This Salesforce DX project packages Arcflare's existing External Client App
from Elevate Prod into a tiny managed 2GP package. The package is intended for
private distribution to customer Salesforce orgs so those orgs can explicitly
trust Arcflare before the OAuth authorization flow starts.

## Source org

- Dev Hub / source org alias: `arcflare-devhub`
- Source org: Elevate Prod
- Namespace: `elemes`
- External Client App API name: `Arcflare`

## Package contents

The package contains only the subscriber-installable ECA metadata:

- `ExternalClientApplication:Arcflare`
- `ExtlClntAppOauthSettings:Arcflare_oauth`

The global OAuth settings file is intentionally not committed or packaged. The
OAuth settings metadata keeps its `oauthLink` to Elevate Prod so installed
subscriber ECAs remain associated with the source org's OAuth consumer
credentials.

The generated OAuth policy metadata is intentionally not packaged because
managed 2GP package version creation rejects
`ExtlClntAppOauthConfigurablePolicies`. Subscriber orgs can manage policies for
the installed ECA from External Client App Manager after install.

## Build commands

Authenticate Elevate Prod before creating future package versions:

```powershell
sf org login web --set-default-dev-hub --alias arcflare-devhub --instance-url https://epms.my.salesforce.com
```

```powershell
sf package create --name "Arcflare OAuth Connector" --description "External Client App package for Arcflare Salesforce OAuth authorization." --package-type Managed --path force-app --target-dev-hub arcflare-devhub
sf package version create --package "Arcflare OAuth Connector" --definition-file config/project-scratch-def.json --installation-key-bypass --code-coverage --target-dev-hub arcflare-devhub --wait 30
sf package version promote --package "<04t package version id>" --target-dev-hub arcflare-devhub --no-prompt
```

Production install URL:

```text
https://login.salesforce.com/packaging/installPackage.apexp?p0=04tUp000001HpyPIAS
```

Sandbox install URL:

```text
https://test.salesforce.com/packaging/installPackage.apexp?p0=04tUp000001HpyPIAS
```

## Released version

- Package id: `0HoUp00000001YnKAI`
- Released subscriber package version id: `04tUp000001HpyPIAS`
- Version: `1.0.0.2`
- Smoke test: installed successfully into `elevate-willdev`.
