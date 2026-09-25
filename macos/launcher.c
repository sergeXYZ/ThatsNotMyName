#include <libgen.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Mach-O entry so the app bundle can carry a sandbox. A shell script cannot. */

int main(void) {
    char raw[4096];
    char dirbuf[4096];
    char appdir[4096];
    char python[4096];
    char script[4096];
    uint32_t size = sizeof(raw);

    if (_NSGetExecutablePath(raw, &size) != 0) {
        fprintf(stderr, "That's Not My Name: cannot find its own path\n");
        return 1;
    }
    strncpy(dirbuf, raw, sizeof(dirbuf) - 1);
    dirbuf[sizeof(dirbuf) - 1] = '\0';
    char *macos = dirname(dirbuf);

    snprintf(appdir, sizeof(appdir), "%s/../Resources/app", macos);
    snprintf(python, sizeof(python), "%s/../Resources/python/bin/python3", macos);
    snprintf(script, sizeof(script), "%s/macos/desktop.py", appdir);

    if (chdir(appdir) != 0) {
        perror("That's Not My Name");
        return 1;
    }
    unsetenv("PYTHONHOME");
    unsetenv("PYTHONPATH");
    unsetenv("PYTHONSTARTUP");
    setenv("PYTHONUNBUFFERED", "1", 1);
    setenv("TNMN_APP", "1", 1);

    execl(python, python, script, (char *)NULL);
    perror("That's Not My Name");
    return 1;
}
