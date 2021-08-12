#include "third_party/python/Include/pyerrors.h"
#include "third_party/python/Python/importdl.h"
/* clang-format off */

/* Support for dynamic loading of extension modules */

extern char *Py_GetProgramName(void);

const char *_PyImport_DynLoadFiletab[] = {".o", NULL};


dl_funcptr _PyImport_FindSharedFuncptr(const char *prefix,
                                       const char *shortname,
                                       const char *pathname, FILE *fp)
{
    char funcname[258];

    PyOS_snprintf(funcname, sizeof(funcname), "%.20s_%.200s", prefix, shortname);
    return dl_loadmod(Py_GetProgramName(), pathname, funcname);
}