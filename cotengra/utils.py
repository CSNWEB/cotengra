"""Various utilities for cotengra.
"""
import collections
import itertools
import math
import operator
import pathlib
import pickle
import random

from functools import reduce, lru_cache, partial
from operator import or_

try:
    from cytoolz import groupby, interleave, unique
except ImportError:

    def getter(index):
        """Adapted from `toolz`."""
        if isinstance(index, list):
            if len(index) == 1:
                index = index[0]
                return lambda x: (x[index],)
            elif index:
                return operator.itemgetter(*index)
            else:
                return lambda x: ()
        else:
            return operator.itemgetter(index)

    def groupby(key, seq):
        """Adapted from `toolz`."""
        if not callable(key):
            key = getter(key)
        d = collections.defaultdict(lambda: [].append)
        for item in seq:
            d[key(item)](item)
        rv = {}
        for k, v in d.items():
            rv[k] = v.__self__
        return rv

    def interleave(seqs):
        """Adapted from `toolz`."""
        iters = itertools.cycle(map(iter, seqs))
        while True:
            try:
                for itr in iters:
                    yield next(itr)
                return
            except StopIteration:
                predicate = partial(operator.is_not, itr)
                iters = itertools.cycle(itertools.takewhile(predicate, iters))

    def unique(it):
        yield from dict.fromkeys(it)


__all__ = ("groupby", "interleave", "unique")


def deprecated(fn, old_name, new_name):
    def new_fn(*args, **kwargs):
        import warnings

        warnings.warn(
            f"The {old_name} function is deprecated in favor of {new_name}",
            Warning,
        )
        return fn(*args, **kwargs)

    return new_fn


def prod(it):
    """Compute the product of sequence of numbers ``it``."""
    x = 1
    for i in it:
        x *= i
    return x


class oset:
    """An ordered set which stores elements as the keys of dict (ordered as of
    python 3.6). 'A few times' slower than using a set directly for small
    sizes, but makes everything deterministic.
    """

    __slots__ = ("_d",)

    def __init__(self, it=()):
        self._d = dict.fromkeys(it)

    @classmethod
    def _from_dict(cls, d):
        obj = object.__new__(oset)
        obj._d = d
        return obj

    @classmethod
    def from_dict(cls, d):
        """Public method makes sure to copy incoming dictionary."""
        return oset._from_dict(d.copy())

    def copy(self):
        return oset.from_dict(self._d)

    def add(self, k):
        self._d[k] = None

    def discard(self, k):
        self._d.pop(k, None)

    def remove(self, k):
        self._d.pop(k)

    def clear(self):
        self._d.clear()

    def update(self, *others):
        for o in others:
            self._d.update(o._d)

    def union(self, *others):
        u = self.copy()
        u.update(*others)
        return u

    def intersection_update(self, *others):
        if len(others) > 1:
            si = set.intersection(*(set(o._d) for o in others))
        else:
            si = others[0]._d
        self._d = {k: None for k in self._d if k in si}

    def intersection(self, *others):
        n_others = len(others)
        if n_others == 0:
            return self.copy()
        elif n_others == 1:
            si = others[0]._d
        else:
            si = set.intersection(*(set(o._d) for o in others))
        return oset._from_dict({k: None for k in self._d if k in si})

    def difference_update(self, *others):
        if len(others) > 1:
            su = set.union(*(set(o._d) for o in others))
        else:
            su = others[0]._d
        self._d = {k: None for k in self._d if k not in su}

    def difference(self, *others):
        if len(others) > 1:
            su = set.union(*(set(o._d) for o in others))
        else:
            su = others[0]._d
        return oset._from_dict({k: None for k in self._d if k not in su})

    def symmetric_difference(self, other):
        return oset._from_dict(
            {
                k: None
                for k in itertools.chain(self._d, other._d)
                if (k not in self._d) or (k not in other)
            }
        )

    def __eq__(self, other):
        if isinstance(other, oset):
            return self._d == other._d
        return False

    def __or__(self, other):
        return self.union(other)

    def __ior__(self, other):
        self.update(other)
        return self

    def __and__(self, other):
        return self.intersection(other)

    def __iand__(self, other):
        self.intersection_update(other)
        return self

    def __sub__(self, other):
        return self.difference(other)

    def __isub__(self, other):
        self.difference_update(other)
        return self

    def __len__(self):
        return self._d.__len__()

    def __iter__(self):
        return self._d.__iter__()

    def __contains__(self, x):
        return self._d.__contains__(x)

    def __repr__(self):
        return f"oset({list(self._d)})"


class MaxCounter:
    """Simple class to keep track of the maximum in a likely changing
    sequence of elements.

    Parameters
    ----------
    it : None or sequence of hashable, optional
        The initial items to add.

    Examples
    --------

        >>> mc = MaxCounter([1, 2, 3, 3])
        >>> mc.max()
        3

        >>> mc.discard(3)
        >>> mc.max()
        3

        >>> mc.discard(3)
        >>> mc.max()
        2

        >>> mc.add(10)
        >>> mc.max()
        10

    """

    __slots__ = ("_c", "_max_element")

    def __init__(self, it=None):
        self._c = collections.Counter(it)
        if it is None:
            self._max_element = -float("inf")
        else:
            self._max_element = max(self._c)

    def copy(self):
        new = object.__new__(MaxCounter)
        new._max_element = self._max_element
        new._c = self._c.copy()
        return new

    def discard(self, x):
        """Discard element ``x`` and possibly update the maximum."""
        cnt = self._c[x]
        if cnt <= 1:
            del self._c[x]
            if x == self._max_element:
                # only need to update the max if ``x``
                # was the last maximum sized element
                try:
                    self._max_element = max(self._c)
                except ValueError:
                    self._max_element = -float("inf")
        else:
            self._c[x] = cnt - 1

    def add(self, x):
        """Add element ``x`` and possibly update the maximum."""
        self._c[x] += 1
        self._max_element = max(self._max_element, x)

    def max(self):
        """The maximum element in this list."""
        return self._max_element


class BitSet:
    __slots__ = ("members", "map", "size", "infimum", "supremum", "hashkey")

    def __init__(self, it):
        self.members = tuple(unique(it))
        self.map = {m: i for i, m in enumerate(self.members)}
        self.size = len(self.members)
        self.supremum = self.fromint(2**self.size - 1)
        self.infimum = self.fromint(0)
        self.hashkey = hash(self.members)

    def asint(self, elem):
        return 1 << self.map[elem]

    def fromint(self, n):
        return BitMembers.fromint(self, n)

    def frommembers(self, it=()):
        return BitMembers.frommembers(self, it)

    __call__ = frommembers


class BitMembers:
    __slots__ = ("i", "bitset")

    @classmethod
    def fromint(cls, bitset, n):
        self = object.__new__(cls)
        self.bitset = bitset
        self.i = n
        return self

    @classmethod
    def frommembers(cls, bitset, it=()):
        self = object.__new__(cls)
        self.bitset = bitset
        self.i = reduce(or_, map(self.bitset.asint, it), 0)
        return self

    def __int__(self):
        return self.i

    __hash__ = __int__

    def __eq__(self, other):
        return (self.i == other.i) and (
            self.bitset.hashkey == other.bitset.hashkey
        )

    def __len__(self):
        return f"{self.i:b}".count("1")

    def __iter__(self):
        return (
            x
            for b, x in zip(bin(self.i)[:1:-1], self.bitset.members)
            if b == "1"
        )

    def add(self, elem):
        self.i |= self.bitset.asint(elem)

    def clear(self):
        self.i = 0

    def copy(self):
        return self.bitset.fromint(self.i)

    def __bool__(self):
        return self.i != 0

    def __contains__(self, elem):
        return self.i & self.bitset.asint(elem)

    def discard(self, elem):
        self.i &= self.bitset.supremum.i - self.bitset.asint(elem)

    def remove(self, elem):
        if elem not in self:
            raise KeyError
        self.discard(elem)

    def difference_update(self, *others):
        for other in others:
            self.i &= ~other.i

    __isub__ = difference_update

    def difference(self, *others):
        bm = self.copy()
        bm.difference_update(*others)
        return bm

    __sub__ = difference

    def intersection_update(self, *others):
        for other in others:
            self.i &= other.i

    __iand__ = intersection_update

    def intersection(self, *others):
        bm = self.copy()
        bm.intersection_update(*others)
        return bm

    __and__ = intersection

    def isdisjoint(self, other):
        return not self.i & other.i

    def issubset(self, other):
        return self.i & other.i == self.i

    def issuperset(self, other):
        return self.i | other.i == self.i

    def symmetric_difference_update(self, other):
        self.i ^= other.i

    __ixor__ = symmetric_difference_update

    def symmetric_difference(self, other):
        return self.bitset.fromint(self.i ^ other.i)

    __xor__ = symmetric_difference

    def update(self, *others):
        self.i = reduce(or_, (o.i for o in others), self.i)

    __ior__ = update

    def union(self, *others):
        return self.bitset.fromint(reduce(or_, (o.i for o in others), self.i))

    __or__ = union

    def __repr__(self):
        return f"<BitMembers({list(self)})>"


class BitSetInt(int):
    """A bitset for keeping track of dense sets of integers. Subclass of
    ``int`` that overrides ``-``,  ``&`` and  ``|`` and provides ``__len__``
    and ``__iter__``. As of python 3.8 doesn't seem much better than using
    frozenset[int] (slower and limited memory savings).

    Parameters
    ----------
    it : Iterable[int] or int
        If sequence of ``int``, treat these as the set members. If raw ``int``
        interpret as bitset directly.
    """

    def __new__(cls, it=0):
        if isinstance(it, int):
            i = it
        else:
            i = reduce(or_, (1 << i for i in it), 0)
        return super(cls, cls).__new__(cls, i)

    def __hash__(self):
        return self + self.bit_length()

    @classmethod
    def infimum(cls):
        return super(cls, cls).__new__(cls, 0)

    @classmethod
    def supremum(cls, size):
        return super(cls, cls).__new__(cls, (1 << size) - 1)

    def __len__(self):
        return f"{self:b}".count("1")

    def iter_sparse(self):
        x = self
        while x:
            i = x.bit_length() - 1
            yield i
            x ^= 1 << i

    def __iter__(self):
        return (x for x, b in enumerate(bin(self)[:1:-1]) if b == "1")

    def __contains__(self, i):
        return bool(self & (1 << i))

    def __sub__(self, i):
        return BitSetInt(int.__and__(self, ~i))

    def difference(self, i):
        return self - i

    def __and__(self, i):
        return BitSetInt(int.__and__(self, i))

    def intersection(self, i):
        return self & i

    def __or__(self, i):
        return BitSetInt(int.__or__(self, i))

    def union(*it):
        return BitSetInt(reduce(int.__or__, it))

    def __repr__(self):
        return f"<BitSetInt({list(self)})>"


try:
    # accelerated bitset iteration
    from cotengra.cotengra import indexes

    def fast_bitmember_iter(self):
        return map(self.bitset.members.__getitem__, indexes(f"{self.i:b}"))

    BitMembers.__iter__ = fast_bitmember_iter

    def fast_bitsetint_iter(self):
        return iter(indexes(f"{self:b}"))

    BitSetInt.__iter__ = fast_bitsetint_iter

except ImportError:
    pass


try:
    # accelerated bitset size
    from gmpy2 import popcount

    def fast_bitmember_len(self):
        return popcount(self.i)

    BitMembers.__len__ = fast_bitmember_len

    def fast_bitsetint_len(self):
        return popcount(self)

    BitSetInt.__len__ = fast_bitsetint_len

except ImportError:
    pass


NODE_TYPE = "frozenset[int]"


if NODE_TYPE == "frozenset[int]":

    def node_from_seq(it):
        return frozenset(it)

    def node_from_single(x):
        return frozenset((x,))

    def node_supremum(size):
        return frozenset(range(size))

    def node_get_single_el(node):
        """Assuming ``node`` has one element, return it."""
        return next(iter(node))

    def is_valid_node(node):
        """Check ``node`` is of type ``frozenset[int]``."""
        try:
            if not isinstance(node, frozenset):
                return False
            el = next(iter(node))
            if not isinstance(el, int):
                return False
            return True
        except TypeError:
            return False

elif NODE_TYPE == "BitSetInt":
    # the set of functions needed to use BitSetInt as contraction tree nodes

    def node_from_seq(it):
        return BitSetInt(it)

    def node_from_single(x):
        return BitSetInt(1 << x)

    def node_supremum(size):
        return BitSetInt.supremum(size)

    def node_get_single_el(node):
        return node.bit_length() - 1

    def is_valid_node(node):
        try:
            return isinstance(node, BitSetInt)
        except TypeError:
            return False

elif NODE_TYPE == "intbitset":
    from intbitset import intbitset

    # intbitset could be great, but hash collisions make use in dicts v v slow

    def node_from_seq(it):
        return intbitset(it)

    def node_from_single(x):
        return intbitset((x,))

    def node_supremum(size):
        return intbitset(range(size))

    def node_get_single_el(node):
        return next(iter(node))

    def is_valid_node(node):
        try:
            return isinstance(node, intbitset)
        except TypeError:
            return False


class DiskDict:
    """A simple persistent dict."""

    __slots__ = ("_directory", "_mem_cache", "_path")

    def __init__(self, directory=None):
        self._mem_cache = {}
        self._directory = directory
        if directory is not None:
            self._path = pathlib.Path(directory)
            self._path.mkdir(parents=True, exist_ok=True)

    def clear(self):
        self._mem_cache.clear()
        if self._directory is not None:
            for p in self._path.glob("*"):
                p.unlink()

    def cleanup(self, delete_dir=False):
        self.clear()
        if delete_dir and (self._directory is not None):
            self._path.rmdir()

    def __contains__(self, k):
        return (k in self._mem_cache) or (
            self._directory is not None and self._path.joinpath(k).exists()
        )

    def __setitem__(self, k, v):
        self._mem_cache[k] = v
        if self._directory is not None:
            fname = self._path.joinpath(k)
            with open(fname, "wb+") as f:
                pickle.dump(v, f)

    def __getitem__(self, k):
        try:
            return self._mem_cache[k]
        except KeyError:
            if self._directory is None:
                raise
            fname = self._path.joinpath(k)
            if not fname.exists():
                raise KeyError

            for _ in range(3):
                try:
                    with open(fname, "rb") as f:
                        self._mem_cache[k] = v = pickle.load(f)
                        return v
                except (EOFError, pickle.UnpicklingError):
                    # file was not written completely yet
                    # e.g. by another process
                    import time

                    time.sleep(0.01)

            raise KeyError


class GumbelBatchedGenerator:
    """Non numpy version of gumbel number generator."""

    def __init__(self, seed=None):
        if isinstance(seed, random.Random):
            self.rng = seed
        else:
            self.rng = random.Random(seed)

    def __call__(self):
        return -math.log(-math.log(self.rng.random()))


class BadTrial(Exception):
    """Use this to indicate that a trial contraction tree was bad."""

    pass


# ---------------------- test equations and utilities ----------------------- #


def compute_size_by_dict(indices, size_dict):
    """Computes the product of sizes of ``indices`` based on ``size_dict``.

    Parameters
    ----------
    indices : iterable[str] or iterable[int]
        The indices of the term.
    size_dict : dict or list
        Mapping (or list/tuple if the indices are indexing integers, which
        can be slightly faster) of indices to sizes.

    Returns
    -------
    d : int
        The resulting product.

    Examples
    --------

        >>> compute_size_by_dict('abbc', {'a': 2, 'b':3, 'c':5})
        90

    """
    d = 1
    for i in indices:
        d *= size_dict[i]
    return d


_einsum_symbols_base = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


@lru_cache(2**14)
def get_symbol(i):
    """Get the symbol corresponding to int ``i`` - runs through the usual 52
    letters before resorting to unicode characters, starting at ``chr(192)``
    and skipping surrogates.

    Examples
    --------

        get_symbol(2)
        #> 'c'

        get_symbol(200)
        #> 'Ŕ'

        get_symbol(20000)
        #> '京'

    """
    if i < 52:
        return _einsum_symbols_base[i]
    elif i >= 55296:
        # Skip chr(57343) - chr(55296) as surrogates
        return chr(i + 2048)
    else:
        return chr(i + 140)


def get_symbol_map(inputs):
    """Get a mapping of arbitrary hashable 'indices' to single unicode symbols,
    matching the canonicalization of the expression.
    """
    symbol_map = {}
    c = 0
    for term in inputs:
        for ind in term:
            if ind not in symbol_map:
                symbol_map[ind] = get_symbol(c)
                c += 1
    return symbol_map


def rand_equation(
    n, reg, n_out=0, n_hyper_in=0, n_hyper_out=0, d_min=2, d_max=3, seed=None
):
    """A more advanced version of ``opt_einsum.helpers.rand_equation`` that
    can also generate both inner and outer hyper-edges. Mostly useful for
    generating test instances covering all edge cases.

    Parameters
    ----------
    n : int
        The number of tensors.
    reg : int
        The average number of indices per tensor if no hyper-edges, i.e.
        total number of inds ``= n * reg // 2``.
    n_out : int, optional
        The number of output indices.
    n_hyper_in : int, optional
        The number of inner hyper-indices.
    n_hyper_out : int, optional
        The number of outer hyper-indices.
    d_min : int, optional
        The minimum dimension size.
    d_max : int, optional
        The maximum dimension size.
    seed : None or int, optional
        Seed for ``np.random`` for repeatibility.

    Returns
    -------
    inputs : list[list[str]]
    output : list[str]
    shapes : list[tuple[int]]
    size_dict : dict[str, int]
    """
    rng = random.Random(seed)

    num_inds = max((n * reg) // 2, n_hyper_out + n_hyper_in + n_out)
    size_dict = {
        get_symbol(i): rng.randint(d_min, d_max) for i in range(num_inds)
    }

    inds = iter(size_dict)
    positions = list(range(n))
    inputs = [[] for _ in range(n)]
    output = []

    for _ in range(n_hyper_out):
        ind = next(inds)
        output.append(ind)
        s = rng.randint(3, n)
        where = rng.sample(positions, s)
        for i in where:
            inputs[i].append(ind)

    for _ in range(n_hyper_in):
        ind = next(inds)
        s = rng.randint(3, n)
        where = rng.sample(positions, s)
        for i in where:
            inputs[i].append(ind)

    for _ in range(n_out):
        ind = next(inds)
        output.append(ind)
        where = rng.sample(positions, 1)
        for i in where:
            inputs[i].append(ind)

    for ind in inds:
        where = rng.sample(positions, 2)
        for i in where:
            inputs[i].append(ind)

    shapes = [tuple(size_dict[ix] for ix in term) for term in inputs]

    rng.shuffle(output)

    return inputs, output, shapes, size_dict


def tree_equation(
    n,
    d_min=2,
    d_max=3,
    n_outer=0,
    seed=None,
):
    """Create a random contraction equation that corresponds to a tree.

    Parameters
    ----------
    n : int
        The number of tensors.
    d_min : int, optional
        The minimum size of an index.
    d_max : int, optional
        The maximum size of an index.
    n_outer : int, optional
        The number of outer indices.
    """
    rng = random.Random(seed)

    inputs = [[]]
    size_dict = {}
    for i in range(1, n):
        ix = get_symbol(i - 1)
        size_dict[ix] = rng.randint(d_min, d_max)
        ci = rng.randint(0, len(inputs) - 1)
        inputs[ci].append(ix)
        inputs.append([ix])

    output = rng.sample(list(size_dict), n_outer)
    shapes = [tuple(size_dict[ix] for ix in term) for term in inputs]

    return inputs, output, shapes, size_dict


def randreg_equation(
    n,
    reg,
    d_min=2,
    d_max=3,
    seed=None,
):
    """Create a random contraction equation that corresponds to a random
    regular graph.

    Parameters
    ----------
    n : int
        The number of terms.
    reg : int
        The degree of the graph.
    d_min : int, optional
        The minimum size of an index.
    d_max : int, optional
        The maximum size of an index.
    seed : None or int, optional
        Seed for ``networkx`` and ``np.random.default_rng`` for repeatibility.

    Returns
    -------
    inputs : list[list[str]]
    output : list[str]
    shapes : list[tuple[int]]
    size_dict : dict[str, int]
    """
    import networkx as nx

    G = nx.random_regular_graph(reg, n, seed=seed)
    inputs = [[] for _ in range(n)]
    for i, (na, nb) in enumerate(G.edges):
        ix = get_symbol(i)
        inputs[na].append(ix)
        inputs[nb].append(ix)

    rng = random.Random(seed)
    size_dict = {
        get_symbol(i): rng.randint(d_min, d_max) for i in range(len(G.edges))
    }

    output = []
    shapes = [tuple(size_dict[ix] for ix in term) for term in inputs]

    return inputs, output, shapes, size_dict


def perverse_equation(
    n,
    num_indices=3,
    min_rank=0,
    max_rank=6,
    d_min=2,
    d_max=3,
    n_outer=2,
    seed=None,
):
    """Create a weird but valid einsum equation with lots of hyper-edges,
    repeated indices, scalars and repeated terms.

    Parameters
    ----------
    n : int
        The number of tensors.
    num_indices : int, optional
        The number of indices to use.
    min_rank : int, optional
        The minimum rank of a tensor.
    max_rank : int, optional
        The maximum rank of a tensor.
    d_min : int, optional
        The minimum size of an index.
    d_max : int, optional
        The maximum size of an index.
    n_outer : int, optional
        The number of outer indices.
    seed : None or int, optional
        Seed for ``random.Random`` for repeatibility.
    """
    rng = random.Random(seed)
    indices = [get_symbol(i) for i in range(num_indices)]

    size_dict = {ix: rng.randint(d_min, d_max) for ix in indices}

    inputs = []
    shapes = []
    for _ in range(n):
        K = rng.randint(min_rank, max_rank)
        term = [rng.choice(indices) for _ in range(K)]
        inputs.append(term)
        shapes.append(tuple(size_dict[ix] for ix in term))

    # can't have more outputs than indices
    n_outer = min(n_outer, num_indices)
    output = rng.sample(indices, n_outer)

    return inputs, output, shapes, size_dict


def rand_tree(
    n,
    reg,
    n_out=0,
    n_hyper_in=0,
    n_hyper_out=0,
    d_min=2,
    d_max=3,
    seed=None,
    optimize="greedy",
):
    from .core import ContractionTree

    inputs, output, _, size_dict = rand_equation(
        n,
        reg,
        n_out=n_out,
        n_hyper_in=n_hyper_in,
        n_hyper_out=n_hyper_out,
        d_min=d_min,
        d_max=d_max,
        seed=seed,
    )
    tree = ContractionTree(inputs, output, size_dict)
    tree.contract_nodes(tuple(tree.gen_leaves()), optimize=optimize)
    return tree


def lattice_equation(dims, cyclic=False, d_min=2, d_max=None, seed=None):
    """Create a random contraction equation that corresponds to a lattice.

    Parameters
    ----------
    dims : sequence of int
        The size of each dimension, with the dimensionality being the length
        of the sequence.
    cyclic : bool or sequence of bool, optional
        Whether each dimension is cyclic or not. If a sequence, must be the
        same length as ``dims``.
    d_min : int, optional
        The minimum size of an index.
    d_max : int, optional
        The maximum size of an index. If ``None``, defaults to ``d_min``, i.e.
        all indices are the same size.
    seed : None or int, optional
        Seed for ``random.Random`` for repeatibility.
    """
    if d_max is None:
        d_max = d_min

    ndim = len(dims)
    try:
        cyclics = tuple(cyclic)
    except TypeError:
        cyclics = (cyclic,) * ndim

    symbol_map = collections.defaultdict(
        map(get_symbol, itertools.count()).__next__
    )

    inputs = []
    for coo_a in itertools.product(*(range(n) for n in dims)):
        term = []
        for s in range(ndim):
            for step in (-1, +1):
                coo_b = list(coo_a)
                coo_b[s] += step
                if cyclics[s]:
                    # wrap-around
                    coo_b[s] %= dims[s]
                elif coo_b[s] < 0 or coo_b[s] >= dims[s]:
                    continue
                coo_b = tuple(coo_b)

                edge = (coo_a, coo_b) if (coo_a < coo_b) else (coo_b, coo_a)
                ix = symbol_map[edge]

                term.append(ix)
        inputs.append(term)

    output = []

    rng = random.Random(seed)
    size_dict = {
        # avoid overflow issues by converting back to python int
        ix: int(rng.randint(d_min, d_max))
        for ix in symbol_map.values()
    }

    shapes = tuple(tuple(size_dict[ix] for ix in term) for term in inputs)

    return inputs, output, shapes, size_dict


def find_output_str(lhs):
    """Compute the output string from the left-hand side only of an equation.
    This is any indices that appear only once in the left-hand side, in sorted
    order.

    Parameters
    ----------
    lhs : str
        The comma separated list of indices on the left-hand side of an
        einsum equation.

    Returns
    -------
    rhs : str
        The output string of the einsum equation.

    Examples
    --------

        >>> find_output_str('cb,ba')
        'ac'
    """
    tmp_lhs = lhs.replace(",", "")
    return "".join(s for s in sorted(set(tmp_lhs)) if tmp_lhs.count(s) == 1)


def eq_to_inputs_output(eq):
    """Convert a einsum equation into an explicit list of list of characters
    and an output list of characters.

    Parameters
    ----------
    eq : str
        The einsum equation, with or without output.

    Returns
    -------
    inputs : list[list[str]]
        The input terms.
    output : list[str]
        The output term.
    """
    lhs, *rhs = eq.split("->")
    inputs = tuple(map(tuple, lhs.split(",")))
    if rhs:
        output = tuple(rhs[0])
    else:
        output = tuple(find_output_str(lhs))
    return inputs, output


def inputs_output_to_eq(inputs, output):
    """Convert an explicit list of inputs and output to a str einsum equation.

    Parameters
    ----------
    inputs : list[list[str]]
        The input terms.
    output : list[str]
        The output term.

    Returns
    -------
    eq : str
        The einsum equation.
    """
    return f"{','.join(map(''.join, inputs))}->{''.join(output)}"


def shapes_inputs_to_size_dict(shapes, inputs):
    """Convert a list of shapes and inputs to a size dictionary.

    Parameters
    ----------
    shapes : list[tuple[int]]
        The shapes of each input.
    inputs : list[list[str]]
        The input terms.

    Returns
    -------
    size_dict : dict[str, int]
        The index size dictionary.
    """
    return {
        ix: d
        for ix, d in zip(
            itertools.chain.from_iterable(inputs),
            itertools.chain.from_iterable(shapes),
        )
    }


def make_rand_size_dict_from_inputs(inputs, d_min=2, d_max=3, seed=None):
    """Get a random size dictionary for a given set of inputs.

    Parameters
    ----------
    inputs : list[list[str]]
        The input terms.
    d_min : int, optional
        The minimum dimension, by default 2.
    d_max : int, optional
        The maximum dimension, by default 3.
    seed : int, optional
        The random seed, by default None.

    Returns
    -------
    size_dict : dict[str, int]
        The index size dictionary.
    """
    rng = random.Random(seed)

    size_dict = {}
    for term in inputs:
        for ix in term:
            if ix not in size_dict:
                size_dict[ix] = rng.randint(d_min, d_max)
    return size_dict


def make_shapes_from_inputs(inputs, size_dict):
    """Make example shapes to match inputs and index sizes.

    Parameters
    ----------
    inputs : list[list[str]]
        The input terms.
    size_dict : dict[str, int]
        The index size dictionary.

    Returns
    -------
    shapes : list[tuple[int]]
        The example shapes.
    """
    return [tuple(size_dict[ix] for ix in term) for term in inputs]


def make_arrays_from_inputs(inputs, size_dict, seed=None):
    """Make example arrays to match inputs and index sizes.

    Parameters
    ----------
    inputs : list[list[str]]
        The input terms.
    size_dict : dict[str, int]
        The index size dictionary.
    seed : int, optional
        The random seed, by default None.

    Returns
    -------
    arrays : list[numpy.ndarray]
        The example arrays.
    """
    import numpy as np

    shapes = make_shapes_from_inputs(inputs, size_dict)
    rng = np.random.default_rng(seed)
    return [rng.normal(size=shape) for shape in shapes]


def make_arrays_from_eq(eq, d_min=2, d_max=3, seed=None):
    """Create a set of example arrays to match an einsum equation directly.

    Parameters
    ----------
    eq : str
        The einsum equation.
    d_min : int, optional
        The minimum dimension, by default 2.
    d_max : int, optional
        The maximum dimension, by default 3.
    seed : int, optional
        The random seed, by default None.

    Returns
    -------
    arrays : list[numpy.ndarray]
        The example arrays.
    """
    inputs, _ = eq_to_inputs_output(eq)
    size_dict = make_rand_size_dict_from_inputs(
        inputs, d_min=d_min, d_max=d_max, seed=seed
    )
    return make_arrays_from_inputs(inputs, size_dict, seed=seed)


def find_output_from_inputs(inputs):
    """Find the output indices for a given set of inputs. The outputs are
    calculated as the set of indices that appear only once, in the order they
    appear in the inputs. This is different to `einsum` where they in sorted
    order since we only require the indices to be hashable.

    Parameters
    ----------
    inputs : Sequence[Sequence[Hashable]]
        The input terms.

    Returns
    -------
    output : tuple[Hashable]
    """
    # need to compute output
    appeared = set()
    once = {}
    for term in inputs:
        for ind in term:
            if ind in appeared:
                # appeared more than once
                once.pop(ind, None)
            else:
                # first appearance
                once[ind] = None
                appeared.add(ind)

    # dict insertion order is same as appearance order
    return tuple(once)


def canonicalize_inputs(inputs, output=None, shapes=None, size_dict=None):
    """Return a canonicalized version of the inputs and output, with the
    indices labelled from 'a', 'b', 'c', ... according to the order they appear
    in the equation.

    If ``output`` is not provided, it will be computed as the set of indices
    that appear once, in the order they appear on the inputs (note that this is
    different to `einsum` where they in sorted order since we only require the
    indices to be hashable and not comparable).

    If either ``shapes`` or ``size_dict`` is provided, then also compute the
    corresponding canonicalized ``size_dict`` for new index labels.

    Parameters
    ----------
    inputs : Sequence[Sequence[Hashable]]
        The input terms.
    output : Sequence[Hashable], optional
        The output term. If not supplied it will be computed.
    shapes : None or Sequence[tuple[int]], optional
        The shapes of each input.
    size_dict : None or dict[Hashable, int], optional
        The index size dictionary.

    Returns
    -------
    inputs : tuple[tuple[str]]
        The canonicalized input terms.
    output : tuple[str]
        The canonicalized output term.
    size_dict : dict[str, int] or None
        The canonicalized index size dictionary, ``None`` if ``size_dict`` or
        ``shapes`` was not provided.
    """
    ind_map = collections.defaultdict(
        map(get_symbol, itertools.count()).__next__
    )

    new_inputs = tuple(tuple(ind_map[ind] for ind in term) for term in inputs)

    if output is not None:
        new_output = tuple(ind_map[ind] for ind in output)
    else:
        new_output = find_output_from_inputs(new_inputs)

    if size_dict is not None:
        new_size_dict = {ind_map[ind]: d for ind, d in size_dict.items()}
    elif shapes is not None:
        new_size_dict = {
            ix: d
            for term, shape in zip(new_inputs, shapes)
            for ix, d in zip(term, shape)
        }
    else:
        new_size_dict = None

    return new_inputs, new_output, new_size_dict
