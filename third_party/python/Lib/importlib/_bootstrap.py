"""Core implementation of import.

This module is NOT meant to be directly imported! It has been designed such
that it can be bootstrapped into Python as the implementation of import. As
such it requires the injection of specific modules and attributes in order to
work. One should use importlib as the public-facing version of this module.

"""
#
# IMPORTANT: Whenever making changes to this module, be sure to run
# a top-level make in order to get the frozen version of the module
# updated. Not doing so will result in the Makefile to fail for
# all others who don't have a ./python around to freeze the module
# in the early stages of compilation.
#

# See importlib._setup() for what is injected into the global namespace.

# When editing this code be aware that code executed at import time CANNOT
# reference any injected objects! This includes not only global code but also
# anything specified at the class level.

# Bootstrap-related code ######################################################

_bootstrap_external = None

def _wrap(new, old):
    """Simple substitute for functools.update_wrapper."""
    for replace in ['__module__', '__name__', '__qualname__', '__doc__']:
        if hasattr(old, replace):
            setattr(new, replace, getattr(old, replace))
    new.__dict__.update(old.__dict__)


# Module-level locking ########################################################

# A dict mapping module names to weakrefs of _ModuleLock instances
# Dictionary protected by the global import lock
_module_locks = {}
# A dict mapping thread ids to _ModuleLock instances
_blocking_on = {}


class _DeadlockError(RuntimeError):
    pass


class _ModuleLock:
    """A recursive lock implementation which is able to detect deadlocks
    (e.g. thread 1 trying to take locks A then B, and thread 2 trying to
    take locks B then A).
    """

    def __init__(self, name):
        self.lock = _thread.allocate_lock()
        self.wakeup = _thread.allocate_lock()
        self.name = name
        self.owner = None
        self.count = 0
        self.waiters = 0

    def has_deadlock(self):
        # Deadlock avoidance for concurrent circular imports.
        me = _thread.get_ident()
        tid = self.owner
        while True:
            lock = _blocking_on.get(tid)
            if lock is None:
                return False
            tid = lock.owner
            if tid == me:
                return True

    def acquire(self):
        """
        Acquire the module lock.  If a potential deadlock is detected,
        a _DeadlockError is raised.
        Otherwise, the lock is always acquired and True is returned.
        """
        tid = _thread.get_ident()
        _blocking_on[tid] = self
        try:
            while True:
                with self.lock:
                    if self.count == 0 or self.owner == tid:
                        self.owner = tid
                        self.count += 1
                        return True
                    if self.has_deadlock():
                        raise _DeadlockError('deadlock detected by %r' % self)
                    if self.wakeup.acquire(False):
                        self.waiters += 1
                # Wait for a release() call
                self.wakeup.acquire()
                self.wakeup.release()
        finally:
            del _blocking_on[tid]

    def release(self):
        tid = _thread.get_ident()
        with self.lock:
            if self.owner != tid:
                raise RuntimeError('cannot release un-acquired lock')
            assert self.count > 0
            self.count -= 1
            if self.count == 0:
                self.owner = None
                if self.waiters:
                    self.waiters -= 1
                    self.wakeup.release()

    def __repr__(self):
        return '_ModuleLock({!r}) at {}'.format(self.name, id(self))


class _DummyModuleLock:
    """A simple _ModuleLock equivalent for Python builds without
    multi-threading support."""

    def __init__(self, name):
        self.name = name
        self.count = 0

    def acquire(self):
        self.count += 1
        return True

    def release(self):
        if self.count == 0:
            raise RuntimeError('cannot release un-acquired lock')
        self.count -= 1

    def __repr__(self):
        return '_DummyModuleLock({!r}) at {}'.format(self.name, id(self))


class _ModuleLockManager:

    def __init__(self, name):
        self._name = name
        self._lock = None

    def __enter__(self):
        self._lock = _get_module_lock(self._name)
        self._lock.acquire()

    def __exit__(self, *args, **kwargs):
        self._lock.release()


# The following two functions are for consumption by Python/import.c.

def _get_module_lock(name):
    """Get or create the module lock for a given module name.

    Acquire/release internally the global import lock to protect
    _module_locks."""

    _imp.acquire_lock()
    try:
        try:
            lock = _module_locks[name]()
        except KeyError:
            lock = None

        if lock is None:
            if _thread is None:
                lock = _DummyModuleLock(name)
            else:
                lock = _ModuleLock(name)

            def cb(ref, name=name):
                _imp.acquire_lock()
                try:
                    # bpo-31070: Check if another thread created a new lock
                    # after the previous lock was destroyed
                    # but before the weakref callback was called.
                    if _module_locks.get(name) is ref:
                        del _module_locks[name]
                finally:
                    _imp.release_lock()

            _module_locks[name] = _weakref.ref(lock, cb)
    finally:
        _imp.release_lock()

    return lock


def _lock_unlock_module(name):
    """Acquires then releases the module lock for a given module name.

    This is used to ensure a module is completely initialized, in the
    event it is being imported by another thread.
    """
    lock = _get_module_lock(name)
    try:
        lock.acquire()
    except _DeadlockError:
        # Concurrent circular import, we'll accept a partially initialized
        # module object.
        pass
    else:
        lock.release()

# Frame stripping magic ###############################################
def _call_with_frames_removed(f, *args, **kwds):
    """remove_importlib_frames in import.c will always remove sequences
    of importlib frames that end with a call to this function

    Use it instead of a normal call in places where including the importlib
    frames introduces unwanted noise into the traceback (e.g. when executing
    module code)
    """
    return f(*args, **kwds)


def _verbose_message(message, *args, verbosity=1):
    """Print the message to stderr if -v/PYTHONVERBOSE is turned on."""
    if sys.flags.verbose >= verbosity:
        if not message.startswith(('#', 'import ')):
            message = '# ' + message
        print(message.format(*args), file=sys.stderr)


def _requires_builtin(fxn):
    """Decorator to verify the named module is built-in."""
    def _requires_builtin_wrapper(self, fullname):
        if fullname not in BUILTIN_MODULE_NAMES:
            raise ImportError('{!r} is not a built-in module'.format(fullname),
                              name=fullname)
        return fxn(self, fullname)
    _wrap(_requires_builtin_wrapper, fxn)
    return _requires_builtin_wrapper


def _requires_frozen(fxn):
    """Decorator to verify the named module is frozen."""
    def _requires_frozen_wrapper(self, fullname):
        if not _imp.is_frozen(fullname):
            raise ImportError('{!r} is not a frozen module'.format(fullname),
                              name=fullname)
        return fxn(self, fullname)
    _wrap(_requires_frozen_wrapper, fxn)
    return _requires_frozen_wrapper


# Typically used by loader classes as a method replacement.
def _load_module_shim(self, fullname):
    """Load the specified module into sys.modules and return it.

    This method is deprecated.  Use loader.exec_module instead.

    """
    spec = spec_from_loader(fullname, self)
    if fullname in sys.modules:
        module = sys.modules[fullname]
        _exec(spec, module)
        return sys.modules[fullname]
    else:
        return _load(spec)

# Module specifications #######################################################

def _module_repr(module):
    # The implementation of ModuleType.__repr__().
    loader = getattr(module, '__loader__', None)
    if hasattr(loader, 'module_repr'):
        # As soon as BuiltinImporter, FrozenImporter, and NamespaceLoader
        # drop their implementations for module_repr. we can add a
        # deprecation warning here.
        try:
            return loader.module_repr(module)
        except Exception:
            pass
    spec = getattr(module, "__spec__", None)
    if spec is not None:
        return _module_repr_from_spec(spec)

    # We could use module.__class__.__name__ instead of 'module' in the
    # various repr permutations.
    name = getattr(module,"__name__", '?')
    filename = getattr(module, "__file__", None)
    if filename is not None:
        return '<module {!r} from {!r}>'.format(name, filename)
    else:
        if loader is None:
            return '<module {!r}>'.format(name)
        else:
            return '<module {!r} ({!r})>'.format(name, loader)


class _installed_safely:

    def __init__(self, module):
        self._module = module
        self._spec = module.__spec__

    def __enter__(self):
        # This must be done before putting the module in sys.modules
        # (otherwise an optimization shortcut in import.c becomes
        # wrong)
        sys.modules[self._spec.name] = self._module

    def __exit__(self, *args):
        spec = self._spec
        if args and any(arg is not None for arg in args):
            sys.modules.pop(spec.name, None)
        else:
            _verbose_message('import {!r} # {!r}', spec.name, spec.loader)

class ModuleSpec:
    """The specification for a module, used for loading.

    A module's spec is the source for information about the module.  For
    data associated with the module, including source, use the spec's
    loader.

    `name` is the absolute name of the module.  `loader` is the loader
    to use when loading the module.  `parent` is the name of the
    package the module is in.  The parent is derived from the name.

    `is_package` determines if the module is considered a package or
    not.  On modules this is reflected by the `__path__` attribute.

    `origin` is the specific location used by the loader from which to
    load the module, if that information is available.  When filename is
    set, origin will match.

    `has_location` indicates that a spec's "origin" reflects a location.
    When this is True, `__file__` attribute of the module is set.

    `cached` is the location of the cached bytecode file, if any.  It
    corresponds to the `__cached__` attribute.

    `submodule_search_locations` is the sequence of path entries to
    search when importing submodules.  If set, is_package should be
    True--and False otherwise.

    Packages are simply modules that (may) have submodules.  If a spec
    has a non-None value in `submodule_search_locations`, the import
    system will consider modules loaded from the spec as packages.

    Only finders (see importlib.abc.MetaPathFinder and
    importlib.abc.PathEntryFinder) should modify ModuleSpec instances.

    """

    def __init__(self, name, loader, *, origin=None, loader_state=None,
                 is_package=None):
        self.name = name
        self.loader = loader
        self.origin = origin
        self.loader_state = loader_state
        self.submodule_search_locations = [] if is_package else None

        # file-location attributes
        self._set_fileattr = False
        self._cached = None

    def __repr__(self):
        args = ['name={!r}'.format(self.name),
                'loader={!r}'.format(self.loader)]
        if self.origin is not None:
            args.append('origin={!r}'.format(self.origin))
        if self.submodule_search_locations is not None:
            args.append('submodule_search_locations={}'
                        .format(self.submodule_search_locations))
        return '{}({})'.format(self.__class__.__name__, ', '.join(args))

    def __eq__(self, other):
        smsl = self.submodule_search_locations
        try:
            return (self.name == other.name and
                    self.loader == other.loader and
                    self.origin == other.origin and
                    smsl == other.submodule_search_locations and
                    self.cached == other.cached and
                    self.has_location == other.has_location)
        except AttributeError:
            return False

    @property
    def cached(self):
        if self._cached is None:
            if self.origin is not None and self._set_fileattr:
                if _bootstrap_external is None:
                    raise NotImplementedError
                self._cached = _bootstrap_external._get_cached(self.origin)
        return self._cached

    @cached.setter
    def cached(self, cached):
        self._cached = cached

    @property
    def parent(self):
        """The name of the module's parent."""
        if self.submodule_search_locations is None:
            return self.name.rpartition('.')[0]
        else:
            return self.name

    @property
    def has_location(self):
        return self._set_fileattr

    @has_location.setter
    def has_location(self, value):
        self._set_fileattr = bool(value)


def spec_from_loader(name, loader, *, origin=None, is_package=None):
    """Return a module spec based on various loader methods."""
    if hasattr(loader, 'get_filename'):
        if _bootstrap_external is None:
            raise NotImplementedError
        spec_from_file_location = _bootstrap_external.spec_from_file_location

        if is_package is None:
            return spec_from_file_location(name, loader=loader)
        search = [] if is_package else None
        return spec_from_file_location(name, loader=loader,
                                       submodule_search_locations=search)

    if is_package is None:
        if hasattr(loader, 'is_package'):
            try:
                is_package = loader.is_package(name)
            except ImportError:
                is_package = None  # aka, undefined
        else:
            # the default
            is_package = False

    return ModuleSpec(name, loader, origin=origin, is_package=is_package)


def _spec_from_module(module, loader=None, origin=None):
    # This function is meant for use in _setup().
    name = module.__name__
    loader = loader or getattr(module, "__loader__", None)
    location = getattr(module, "__file__", None)
    origin = origin or location or getattr(loader, "_ORIGIN", None)
    cached = getattr(module, "__cached__", None)
    submodule_search_locations = getattr(module, "__path__", None)
    if submodule_search_locations is not None:
        submodule_search_locations = list(submodule_search_locations)

    spec = ModuleSpec(name, loader, origin=origin)
    spec._set_fileattr = location is not None
    spec.cached = cached
    spec.submodule_search_locations = submodule_search_locations
    return spec



def _init_module_attrs(spec, module, *, override=False):
    if override:
        module.__name__ = spec.name
        module.__loader__ = spec.loader
        module.__package__ = spec.parent
        module.__path__ = None or spec.submodule_search_locations
        if spec.has_location:
            module.__file__ = None or spec.origin
            module.__cached__ = None or spec.cached
    else:
        module.__name__ = getattr(module, "__name__", None) or spec.name
        module.__loader__ = getattr(module, "__loader__", None) or spec.loader
        module.__package__ = getattr(module, "__package__", None) or spec.parent
        module.__path__ = getattr(module, "__path__", None) or spec.submodule_search_locations
        if spec.has_location:
            module.__file__ = getattr(module, "__file__", None) or spec.origin
            module.__cached__ = getattr(module, "__cached__", None) or spec.cached

    module.__spec__ = getattr(module, "__spec__", None) or spec
    if module.__loader__ is None:
        # A backward compatibility hack.
        if spec.submodule_search_locations is not None:
            if _bootstrap_external is None:
                raise NotImplementedError
            _NamespaceLoader = _bootstrap_external._NamespaceLoader
            module.__loader__ = _NamespaceLoader.__new__(_NamespaceLoader)
            module.__loader__._path = spec.submodule_search_locations

    return module


def module_from_spec(spec):
    """Create a module based on the provided spec."""
    # Typically loaders will not implement create_module().
    module = None
    if hasattr(spec.loader, 'create_module'):
        # If create_module() returns `None` then it means default
        # module creation should be used.
        module = spec.loader.create_module(spec)
    elif hasattr(spec.loader, 'exec_module'):
        raise ImportError('loaders that define exec_module() '
                          'must also define create_module()')
    if module is None:
        module = type(sys)(spec.name)
    _init_module_attrs(spec, module)
    return module


def _module_repr_from_spec(spec):
    """Return the repr to use for the module."""
    # We mostly replicate _module_repr() using the spec attributes.
    name = '?' if spec.name is None else spec.name
    if spec.origin is None:
        if spec.loader is None:
            return '<module {!r}>'.format(name)
        else:
            return '<module {!r} ({!r})>'.format(name, spec.loader)
    else:
        if spec.has_location:
            return '<module {!r} from {!r}>'.format(name, spec.origin)
        else:
            return '<module {!r} ({})>'.format(spec.name, spec.origin)


# Used by importlib.reload() and _load_module_shim().
def _exec(spec, module):
    """Execute the spec's specified module in an existing module's namespace."""
    name = spec.name
    if sys.modules.get(name) is not module:
        msg = 'module {!r} not in sys.modules'.format(name)
        raise ImportError(msg, name=name)
    if spec.loader is None:
        if spec.submodule_search_locations is None:
            raise ImportError('missing loader', name=spec.name)
        # namespace package
        _init_module_attrs(spec, module, override=True)
        return module
    _init_module_attrs(spec, module, override=True)
    if not hasattr(spec.loader, 'exec_module'):
        # (issue19713) Once BuiltinImporter and ExtensionFileLoader
        # have exec_module() implemented, we can add a deprecation
        # warning here.
        spec.loader.load_module(name)
    else:
        spec.loader.exec_module(module)
    return sys.modules[name]


def _load_backward_compatible(spec):
    # (issue19713) Once BuiltinImporter and ExtensionFileLoader
    # have exec_module() implemented, we can add a deprecation
    # warning here.
    spec.loader.load_module(spec.name)
    # The module must be in sys.modules at this point!
    module = sys.modules[spec.name]
    if getattr(module, '__loader__', None) is None:
        try:
            module.__loader__ = spec.loader
        except AttributeError:
            pass
    if getattr(module, '__package__', None) is None:
        try:
            # Since module.__path__ may not line up with
            # spec.submodule_search_paths, we can't necessarily rely
            # on spec.parent here.
            module.__package__ = module.__name__
            if not hasattr(module, '__path__'):
                module.__package__ = spec.name.rpartition('.')[0]
        except AttributeError:
            pass
    if getattr(module, '__spec__', None) is None:
        try:
            module.__spec__ = spec
        except AttributeError:
            pass
    return module

def _load_unlocked(spec):
    # A helper for direct use by the import system.
    if spec.loader is not None:
        # not a namespace package
        if not hasattr(spec.loader, 'exec_module'):
            return _load_backward_compatible(spec)

    module = module_from_spec(spec)
    with _installed_safely(module):
        if spec.loader is None:
            if spec.submodule_search_locations is None:
                raise ImportError('missing loader', name=spec.name)
            # A namespace package so do nothing.
        else:
            spec.loader.exec_module(module)

    # We don't ensure that the import-related module attributes get
    # set in the sys.modules replacement case.  Such modules are on
    # their own.
    return sys.modules[spec.name]

# A method used during testing of _load_unlocked() and by
# _load_module_shim().
def _load(spec):
    """Return a new module object, loaded by the spec's loader.

    The module is not added to its parent.

    If a module is already in sys.modules, that existing module gets
    clobbered.

    """
    return _load_unlocked(spec)


# Loaders #####################################################################

class BuiltinImporter:

    """Meta path import for built-in modules.

    All methods are either class or static methods to avoid the need to
    instantiate the class.

    """

    @staticmethod
    def module_repr(module):
        """Return repr for the module.

        The method is deprecated.  The import machinery does the job itself.

        """
        return '<module {!r} (built-in)>'.format(module.__name__)

    @classmethod
    def find_spec(cls, fullname, path=None, target=None):
        if path is not None:
            return None
        if fullname in BUILTIN_MODULE_NAMES:
            return spec_from_loader(fullname, cls, origin='built-in')
        else:
            return None

    @classmethod
    def find_module(cls, fullname, path=None):
        """Find the built-in module.

        If 'path' is ever specified then the search is considered a failure.

        This method is deprecated.  Use find_spec() instead.

        """
        spec = cls.find_spec(fullname, path)
        return spec.loader if spec is not None else None

    @classmethod
    def create_module(self, spec):
        """Create a built-in module"""
        if spec.name not in BUILTIN_MODULE_NAMES:
            raise ImportError('{!r} is not a built-in module'.format(spec.name),
                              name=spec.name)
        return _call_with_frames_removed(_imp.create_builtin, spec)

    @classmethod
    def exec_module(self, module):
        """Exec a built-in module"""
        _call_with_frames_removed(_imp.exec_builtin, module)

    @classmethod
    @_requires_builtin
    def get_code(cls, fullname):
        """Return None as built-in modules do not have code objects."""
        return None

    @classmethod
    @_requires_builtin
    def get_source(cls, fullname):
        """Return None as built-in modules do not have source code."""
        return None

    @classmethod
    @_requires_builtin
    def is_package(cls, fullname):
        """Return False as built-in modules are never packages."""
        return False

    load_module = classmethod(_load_module_shim)


class FrozenImporter:

    """Meta path import for frozen modules.

    All methods are either class or static methods to avoid the need to
    instantiate the class.

    """

    @staticmethod
    def module_repr(m):
        """Return repr for the module.

        The method is deprecated.  The import machinery does the job itself.

        """
        return '<module {!r} (frozen)>'.format(m.__name__)

    @classmethod
    def find_spec(cls, fullname, path=None, target=None):
        if _imp.is_frozen(fullname):
            return spec_from_loader(fullname, cls, origin='frozen')
        else:
            return None

    @classmethod
    def find_module(cls, fullname, path=None):
        """Find a frozen module.

        This method is deprecated.  Use find_spec() instead.

        """
        return cls if _imp.is_frozen(fullname) else None

    @classmethod
    def create_module(cls, spec):
        """Use default semantics for module creation."""

    @staticmethod
    def exec_module(module):
        name = module.__spec__.name
        if not _imp.is_frozen(name):
            raise ImportError('{!r} is not a frozen module'.format(name),
                              name=name)
        code = _call_with_frames_removed(_imp.get_frozen_object, name)
        exec(code, module.__dict__)

    @classmethod
    def load_module(cls, fullname):
        """Load a frozen module.

        This method is deprecated.  Use exec_module() instead.

        """
        return _load_module_shim(cls, fullname)

    @classmethod
    @_requires_frozen
    def get_code(cls, fullname):
        """Return the code object for the frozen module."""
        return _imp.get_frozen_object(fullname)

    @classmethod
    @_requires_frozen
    def get_source(cls, fullname):
        """Return None as frozen modules do not have source code."""
        return None

    @classmethod
    @_requires_frozen
    def is_package(cls, fullname):
        """Return True if the frozen module is a package."""
        return _imp.is_frozen_package(fullname)


# Import itself ###############################################################

class _ImportLockContext:

    """Context manager for the import lock."""

    def __enter__(self):
        """Acquire the import lock."""
        _imp.acquire_lock()

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """Release the import lock regardless of any raised exceptions."""
        _imp.release_lock()


def _resolve_name(name, package, level):
    """Resolve a relative module name to an absolute one."""
    bits = package.rsplit('.', level - 1)
    if len(bits) < level:
        raise ValueError('attempted relative import beyond top-level package')
    base = bits[0]
    return '{}.{}'.format(base, name) if name else base


def _find_spec_legacy(finder, name, path):
    # This would be a good place for a DeprecationWarning if
    # we ended up going that route.
    loader = finder.find_module(name, path)
    if loader is None:
        return None
    return spec_from_loader(name, loader)


def _find_spec(name, path, target=None):
    """Find a module's spec."""
    meta_path = sys.meta_path
    if meta_path is None:
        # PyImport_Cleanup() is running or has been called.
        raise ImportError("sys.meta_path is None, Python is likely "
                          "shutting down")

    if not meta_path:
        _warnings.warn('sys.meta_path is empty', ImportWarning)

    # We check sys.modules here for the reload case.  While a passed-in
    # target will usually indicate a reload there is no guarantee, whereas
    # sys.modules provides one.
    is_reload = name in sys.modules
    for finder in meta_path:
        try:
            find_spec = finder.find_spec
        except AttributeError:
            spec = _find_spec_legacy(finder, name, path)
            if spec is None:
                continue
        else:
            spec = find_spec(name, path, target)
        if spec is not None:
            # The parent import may have already imported this module.
            if not is_reload and name in sys.modules:
                module = sys.modules[name]
                try:
                    __spec__ = module.__spec__
                except AttributeError:
                    # We use the found spec since that is the one that
                    # we would have used if the parent module hadn't
                    # beaten us to the punch.
                    return spec
                else:
                    if __spec__ is None:
                        return spec
                    else:
                        return __spec__
            else:
                return spec
    else:
        return None


def _sanity_check(name, package, level):
    """Verify arguments are "sane"."""
    if not isinstance(name, str):
        raise TypeError('module name must be str, not {}'.format(type(name)))
    if level < 0:
        raise ValueError('level must be >= 0')
    if level > 0:
        if not isinstance(package, str):
            raise TypeError('__package__ not set to a string')
        elif not package:
            raise ImportError('attempted relative import with no known parent '
                              'package')
    if not name and level == 0:
        raise ValueError('Empty module name')


_ERR_MSG_PREFIX = 'No module named '
_ERR_MSG = _ERR_MSG_PREFIX + '{!r}'

def _find_and_load_unlocked(name, import_):
    path = None
    parent = name.rpartition('.')[0]
    if parent:
        if parent not in sys.modules:
            _call_with_frames_removed(import_, parent)
        # Crazy side-effects!
        if name in sys.modules:
            return sys.modules[name]
        parent_module = sys.modules[parent]
        try:
            path = parent_module.__path__
        except AttributeError:
            msg = (_ERR_MSG + '; {!r} is not a package').format(name, parent)
            raise ModuleNotFoundError(msg, name=name) from None
    spec = _find_spec(name, path)
    if spec is None and name in BUILTIN_MODULE_NAMES:
        # If this module is a C extension, the interpreter
        # expects it to be a shared object located in path,
        # and returns spec is None because it was not found.
        #
        # however, if it is a C extension, we can check if it
        # is available using sys.builtin_module_names,
        # because the APE is statically compiled.
        #
        # if the module is present as a builtin, we call
        # BuiltinImporter with the full name (and no path)
        # to create the module spec correctly.
        spec = BuiltinImporter.find_spec(name)
    if spec is None:
        raise ModuleNotFoundError(_ERR_MSG.format(name), name=name)
    else:
        module = _load_unlocked(spec)
    if parent:
        # Set the module as an attribute on its parent.
        parent_module = sys.modules[parent]
        setattr(parent_module, name.rpartition('.')[2], module)
    return module


_NEEDS_LOADING = object()


def _find_and_load(name, import_):
    """Find and load the module."""
    module = sys.modules.get(name, _NEEDS_LOADING)
    if module is _NEEDS_LOADING:
        return _find_and_load_unlocked(name, import_)

    if module is None:
        message = ('import of {} halted; '
                   'None in sys.modules'.format(name))
        raise ModuleNotFoundError(message, name=name)

    return module


def _gcd_import(name, package=None, level=0):
    """Import and return the module based on its name, the package the call is
    being made from, and the level adjustment.

    This function represents the greatest common denominator of functionality
    between import_module and __import__. This includes setting __package__ if
    the loader did not.

    """
    _sanity_check(name, package, level)
    if level > 0:
        name = _resolve_name(name, package, level)
    return _find_and_load(name, _gcd_import)


def _handle_fromlist(module, fromlist, import_, *, recursive=False):
    """Figure out what __import__ should return.

    The import_ parameter is a callable which takes the name of module to
    import. It is required to decouple the function from assuming importlib's
    import implementation is desired.

    """
    # The hell that is fromlist ...
    # If a package was imported, try to import stuff from fromlist.
    if hasattr(module, '__path__'):
        for x in fromlist:
            if not isinstance(x, str):
                if recursive:
                    where = module.__name__ + '.__all__'
                else:
                    where = "``from list''"
                raise TypeError(f"Item in {where} must be str, "
                                f"not {type(x).__name__}")
            elif x == '*':
                if not recursive and hasattr(module, '__all__'):
                    _handle_fromlist(module, module.__all__, import_,
                                     recursive=True)
            elif not hasattr(module, x):
                from_name = '{}.{}'.format(module.__name__, x)
                try:
                    _call_with_frames_removed(import_, from_name)
                except ModuleNotFoundError as exc:
                    # Backwards-compatibility dictates we ignore failed
                    # imports triggered by fromlist for modules that don't
                    # exist.
                    if (exc.name == from_name and
                        sys.modules.get(from_name, _NEEDS_LOADING) is not None):
                        continue
                    raise
    return module


def _calc___package__(globals):
    """Calculate what __package__ should be.

    __package__ is not guaranteed to be defined or could be set to None
    to represent that its proper value is unknown.

    """
    package = globals.get('__package__')
    spec = globals.get('__spec__')
    if package is not None:
        if spec is not None and package != spec.parent:
            _warnings.warn("__package__ != __spec__.parent "
                           f"({package!r} != {spec.parent!r})",
                           ImportWarning, stacklevel=3)
        return package
    elif spec is not None:
        return spec.parent
    else:
        _warnings.warn("can't resolve package from __spec__ or __package__, "
                       "falling back on __name__ and __path__",
                       ImportWarning, stacklevel=3)
        package = globals['__name__']
        if '__path__' not in globals:
            package = package.rpartition('.')[0]
    return package


def __import__(name, globals=None, locals=None, fromlist=(), level=0):
    """Import a module.

    The 'globals' argument is used to infer where the import is occurring from
    to handle relative imports. The 'locals' argument is ignored. The
    'fromlist' argument specifies what should exist as attributes on the module
    being imported (e.g. ``from module import <fromlist>``).  The 'level'
    argument represents the package location to import from in a relative
    import (e.g. ``from ..pkg import mod`` would have a 'level' of 2).

    """
    if level == 0:
        module = _gcd_import(name)
    else:
        globals_ = globals if globals is not None else {}
        package = _calc___package__(globals_)
        module = _gcd_import(name, package, level)
    if not fromlist:
        # Return up to the first dot in 'name'. This is complicated by the fact
        # that 'name' may be relative.
        if level == 0:
            return _gcd_import(name.partition('.')[0])
        elif not name:
            return module
        else:
            # Figure out where to slice the module's name up to the first dot
            # in 'name'.
            cut_off = len(name) - len(name.partition('.')[0])
            # Slice end needs to be positive to alleviate need to special-case
            # when ``'.' not in name``.
            return sys.modules[module.__name__[:len(module.__name__)-cut_off]]
    else:
        return _handle_fromlist(module, fromlist, _gcd_import)


def _builtin_from_name(name):
    spec = BuiltinImporter.find_spec(name)
    if spec is None:
        raise ImportError('no built-in module named ' + name)
    return _load_unlocked(spec)


def _setup(sys_module, _imp_module):
    """Setup importlib by importing needed built-in modules and injecting them
    into the global namespace.

    As sys is needed for sys.modules access and _imp is needed to load built-in
    modules, those two modules must be explicitly passed in.

    """
    global _imp, sys, BUILTIN_MODULE_NAMES
    _imp = _imp_module
    sys = sys_module
    BUILTIN_MODULE_NAMES = frozenset(sys.builtin_module_names)

    # Set up the spec for existing builtin/frozen modules.
    module_type = type(sys)
    for name, module in sys.modules.items():
        if isinstance(module, module_type):
            if name in BUILTIN_MODULE_NAMES:
                loader = BuiltinImporter
            elif _imp.is_frozen(name):
                loader = FrozenImporter
            else:
                continue
            spec = getattr(module, "__spec__", None) or _spec_from_module(module, loader)
            _init_module_attrs(spec, module)

    # Directly load built-in modules needed during bootstrap.
    self_module = sys.modules[__name__]
    for builtin_name in ('_warnings', '_weakref'):
        builtin_module = sys.modules.get(builtin_name, _builtin_from_name(builtin_name))
        setattr(self_module, builtin_name, builtin_module)
    setattr(self_module, '_thread', None)


def _install(sys_module, _imp_module):
    """Install importlib as the implementation of import."""
    _setup(sys_module, _imp_module)

    sys.meta_path.append(BuiltinImporter)
    sys.meta_path.append(FrozenImporter)

    global _bootstrap_external
    import _frozen_importlib_external
    _bootstrap_external = _frozen_importlib_external
    _frozen_importlib_external._install(sys.modules[__name__])
