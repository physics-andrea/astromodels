__author__ = 'giacomov'
# DMFitFunction and DMSpectra add by Andrea Albert (aalbert@slac.stanford.edu) Oct 26, 2016

import math
import numpy as np
import warnings
from scipy.special import gammaincc, gamma, erfcinv
import exceptions

from astromodels.functions.function import Function1D, Function2D, FunctionMeta, ModelAssertionViolation

from astromodels.units import get_units
import astropy.units as astropy_units

import astromodels
from scipy.interpolate import RegularGridInterpolator


class GSLNotAvailable(ImportWarning):
    pass


class NaimaNotAvailable(ImportWarning):
    pass


class InvalidUsageForFunction(exceptions.Exception):
    pass


# Now let's try and import optional dependencies

try:

    # Naima is for numerical computation of Synch. and Inverse compton spectra in randomly oriented
    # magnetic fields

    import naima
    import astropy.units as u

except ImportError:

    warnings.warn("The naima package is not available. Models that depend on it will not be available",
                  NaimaNotAvailable)

    has_naima = False

else:

    has_naima = True

try:

    # GSL is the GNU Scientific Library. Pygsl is the python wrapper for it. It is used by some
    # functions for faster computation

    from pygsl.testing.sf import gamma_inc

except ImportError:

    warnings.warn("The GSL library or the pygsl wrapper cannot be loaded. Models that depend on it will not be "
                  "available.", GSLNotAvailable)

    has_gsl = False

else:

    has_gsl = True


# noinspection PyPep8Naming
class Powerlaw(Function1D):
    r"""
    description :

        A simple power-law

    latex : $ K~\frac{x}{piv}^{index} $

    parameters :

        K :

            desc : Normalization (differential flux at the pivot value)
            initial value : 1.0

        piv :

            desc : Pivot value
            initial value : 1
            fix : yes

        index :

            desc : Photon index
            initial value : -2
            min : -10
            max : 10

    tests :
        - { x : 10, function value: 0.01, tolerance: 1e-20}
        - { x : 100, function value: 0.0001, tolerance: 1e-20}

    """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):
        # The index is always dimensionless
        self.index.unit = astropy_units.dimensionless_unscaled

        # The pivot energy has always the same dimension as the x variable
        self.piv.unit = x_unit

        # The normalization has the same units as the y

        self.K.unit = y_unit

    # noinspection PyPep8Naming
    def evaluate(self, x, K, piv, index):
        xx = np.divide(x, piv)

        return K * np.power(xx, index)


# noinspection PyPep8Naming
class Powerlaw_flux(Function1D):
    r"""
        description :

            A simple power-law with the photon flux in a band used as normalization. This will reduce the correlation
            between the index and the normalization.

        latex : $ \frac{F(\gamma+1)} {b^{\gamma+1} - a^{\gamma+1}} (x)^{\gamma}$

        parameters :

            F :

                desc : Integral between a and b
                initial value : 1

            index :

                desc : Photon index
                initial value : -2
                min : -10
                max : 10

            a :

                desc : lower bound for the band in which computing the integral F
                initial value : 1.0
                fix : yes

            b :

                desc : upper bound for the band in which computing the integral F
                initial value : 100.0
                fix : yes

        """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):
        # The flux is the integral over x, so:
        self.F.unit = y_unit * x_unit

        # The index is always dimensionless
        self.index.unit = astropy_units.dimensionless_unscaled

        # a and b have the same units as x

        self.a.unit = x_unit
        self.b.unit = x_unit

    # noinspection PyPep8Naming
    def evaluate(self, x, F, index, a, b):
        gp1 = index + 1

        return F * gp1 / (b ** gp1 - a ** gp1) * np.power(x, index)


class Cutoff_powerlaw(Function1D):
    r"""
    description :

        A power law multiplied by an exponential cutoff

    latex : $ K~\frac{x}{piv}^{index}~\exp{(-x/xc)} $

    parameters :

        K :

            desc : Normalization (differential flux at the pivot value)
            initial value : 1.0

        piv :

            desc : Pivot value
            initial value : 1
            fix : yes

        index :

            desc : Photon index
            initial value : -2
            min : -10
            max : 10

        xc :

            desc : Photon index
            initial value : 10.0
            min : 1.0

    """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):
        # The index is always dimensionless
        self.index.unit = astropy_units.dimensionless_unscaled

        # The pivot energy has always the same dimension as the x variable
        self.piv.unit = x_unit

        # The cutoff has the same dimensions as x
        self.xc.unit = x_unit

        # The normalization has the same units as the y

        self.K.unit = y_unit

    # noinspection PyPep8Naming
    def evaluate(self, x, K, piv, index, xc):
        return K * np.power(np.divide(x, piv), index) * np.exp(-1 * np.divide(x, xc))


class SmoothlyBrokenPowerLaw(Function1D):
    r"""
    description :

        A Smoothly Broken Power Law

    latex : $  $

    parameters :

        K :

            desc : normalization
            initial value : 1
            min : 0
    

        alpha :

            desc : power law index below the break
            initial value : -1
            min : -1.5
            max : 2

        break_energy:

            desc: location of the peak
            initial value : 300
            fix : no
            min : 10

        break_scale :

            desc: smoothness of the break
            initial value : 0.5
            min : 0.
            max : 10.
            fix : yes

        beta:

            desc : power law index above the break
            initial value : -2.
            min : -5.0
            max : -1.6

        pivot:

            desc: where the spectrum is normalized
            initial value : 100.
            fix: yes


    """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):

        # norm has same unit as energy
        self.K.unit = y_unit

        self.break_energy.unit = x_unit

        self.pivot.unit = x_unit

        self.alpha.unit = astropy_units.dimensionless_unscaled
        self.beta.unit = astropy_units.dimensionless_unscaled
        self.break_scale.unit = astropy_units.dimensionless_unscaled

    def evaluate(self, x, K, alpha, break_energy, break_scale, beta, pivot):

        B = (alpha + beta) / 2.0
        M = (beta - alpha) / 2.0

        arg_piv = np.log10(pivot / break_energy) / break_scale

        if arg_piv < -6.0:
            pcosh_piv = M * break_scale * (-arg_piv - np.log(2.0))
        elif arg_piv > 4.0:

            pcosh_piv = M * break_scale * (arg_piv - np.log(2.0))
        else:
            pcosh_piv = M * break_scale * (np.log((np.exp(arg_piv) + np.exp(-arg_piv)) / 2.0))

        arg = np.log10(x / break_energy) / break_scale
        idx1 = arg < -6.0
        idx2 = arg > 4.0
        idx3 = ~np.logical_or(idx1, idx2)

        # The K * 0 part is a trick so that out will have the right units (if the input
        # has units)

        pcosh = np.zeros(x.shape)

        pcosh[idx1] = M * break_scale * (-arg[idx1] - np.log(2.0))
        pcosh[idx2] = M * break_scale * (arg[idx2] - np.log(2.0))
        pcosh[idx3] = M * break_scale * (np.log((np.exp(arg[idx3]) + np.exp(-arg[idx3])) / 2.0))

        return K * (x / pivot) ** B * 10. ** (pcosh - pcosh_piv)


class Broken_powerlaw(Function1D):
    r"""
    description :

        A broken power law function

    latex : $ f(x)= K~\begin{cases}\left( \frac{x}{x_{b}} \right)^{\alpha} & x < x_{b} \\ \left( \frac{x}{x_{b}} \right)^{\beta} & x \ge x_{b} \end{cases} $

    parameters :

        K :

            desc : Normalization (differential flux at x_b)
            initial value : 1.0

        xb :

            desc : Break point
            initial value : 10
            min : 1.0

        alpha :

            desc : Index before the break xb
            initial value : -1.5
            min : -10
            max : 10

        beta :

            desc : Index after the break xb
            initial value : -2.5
            min : -10
            max : 10

        piv :

            desc : Pivot energy
            initial value : 1.0
            fix : yes

    """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):
        # The normalization has the same units as y
        self.K.unit = y_unit

        # The break point has always the same dimension as the x variable
        self.xb.unit = x_unit

        # alpha and beta are dimensionless
        self.alpha.unit = astropy_units.dimensionless_unscaled
        self.beta.unit = astropy_units.dimensionless_unscaled

        self.piv.unit = x_unit

    # noinspection PyPep8Naming
    def evaluate(self, x, K, xb, alpha, beta, piv):
        # The K * 0 is to keep the units right. If the input has unit, this will make a result
        # array with the same units as K. If the input has no units, this will have no
        # effect whatsoever

        result = np.zeros(x.shape) * K * 0

        idx = (x < xb)
        result[idx] = K * np.power(x[idx] / piv, alpha)
        result[~idx] = K * np.power(xb / piv, alpha - beta) * np.power(x[~idx] / piv, beta)

        return result


# noinspection PyPep8Naming
class Gaussian(Function1D):
    r"""
    description :

        A Gaussian function

    latex : $ K \frac{1}{\sigma \sqrt{2 \pi}}\exp{\frac{(x-\mu)^2}{2~(\sigma)^2}} $

    parameters :

        F :

            desc : Integral between -inf and +inf. Fix this to 1 to obtain a Normal distribution
            initial value : 1

        mu :

            desc : Central value
            initial value : 0.0

        sigma :

            desc : standard deviation
            initial value : 1.0
            min : 1e-12

    tests :
        - { x : 0.0, function value: 0.3989422804014327, tolerance: 1e-10}
        - { x : -1.0, function value: 0.24197072451914337, tolerance: 1e-9}

    """

    __metaclass__ = FunctionMeta

    # Place this here to avoid recomputing it all the time

    __norm_const = 1.0 / (math.sqrt(2 * np.pi))

    def _set_units(self, x_unit, y_unit):

        # The normalization is the integral from -inf to +inf, i.e., has dimensions of
        # y_unit * x_unit
        self.F.unit = y_unit * x_unit

        # The mu has the same dimensions as the x
        self.mu.unit = x_unit

        # sigma has the same dimensions as x
        self.sigma.unit = x_unit

    # noinspection PyPep8Naming
    def evaluate(self, x, F, mu, sigma):

        norm = self.__norm_const / sigma

        return F * norm * np.exp(-np.power(x - mu, 2.) / (2 * np.power(sigma, 2.)))

    def from_unit_cube(self, x):
        """
        Used by multinest

        :param x: 0 < x < 1
        :param lower_bound:
        :param upper_bound:
        :return:
        """

        mu = self.mu.value
        sigma = self.sigma.value

        sqrt_two = 1.414213562

        if x < 1e-16 or (1 - x) < 1e-16:

            res = -1e32

        else:

            res = mu + sigma * sqrt_two * erfcinv(2 * (1 - x))

        return res


class Uniform_prior(Function1D):
    r"""
    description :

        A function which is constant on the interval lower_bound - upper_bound and 0 outside the interval. The
        extremes of the interval are counted as part of the interval.

    latex : $ f(x)=\begin{cases}0 & x < \text{lower_bound} \\\text{value} & \text{lower_bound} \le x \le \text{upper_bound} \\ 0 & x > \text{upper_bound} \end{cases}$

    parameters :

        lower_bound :

            desc : Lower bound for the interval
            initial value : 0
            min : -np.inf
            max : np.inf

        upper_bound :

            desc : Upper bound for the interval
            initial value : 1
            min : -np.inf
            max : np.inf

        value :

            desc : Value in the interval
            initial value : 1.0

    tests :
        - { x : 0.5, function value: 1.0, tolerance: 1e-20}
        - { x : -0.5, function value: 0, tolerance: 1e-20}

    """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):
        # Lower and upper bound has the same unit as x
        self.lower_bound.unit = x_unit
        self.upper_bound.unit = x_unit

        # value has the same unit as y
        self.value.unit = y_unit

    def evaluate(self, x, lower_bound, upper_bound, value):
        # The value * 0 is to keep the units right

        result = np.zeros(x.shape) * value * 0

        idx = (x >= lower_bound) & (x <= upper_bound)
        result[idx] = value

        return result

    def from_unit_cube(self, x):
        """
        Used by multinest

        :param x: 0 < x < 1
        :param lower_bound:
        :param upper_bound:
        :return:
        """

        lower_bound = self.lower_bound.value
        upper_bound = self.upper_bound.value

        low = lower_bound
        spread = float(upper_bound - lower_bound)

        par = x * spread + low

        return par


class Log_uniform_prior(Function1D):
    r"""
    description :

        A function which is K/x on the interval lower_bound - upper_bound and 0 outside the interval. The
        extremes of the interval are NOT counted as part of the interval. Lower_bound must be >= 0.

    latex : $ f(x)=K~\begin{cases}0 & x \le \text{lower_bound} \\\frac{1}{x} & \text{lower_bound} < x < \text{upper_bound} \\ 0 & x \ge \text{upper_bound} \end{cases}$

    parameters :

        lower_bound :

            desc : Lower bound for the interval
            initial value : 1e-20
            min : 1e-30
            max : np.inf

        upper_bound :

            desc : Upper bound for the interval
            initial value : 100
            min : 1e-30
            max : np.inf

        K :

            desc : Normalization
            initial value : 1
            fix : yes

    """

    __metaclass__ = FunctionMeta

    def _setup(self):
        self._handle_units = False

    def _set_units(self, x_unit, y_unit):
        # Lower and upper bound has the same unit as x
        self.lower_bound.unit = x_unit
        self.upper_bound.unit = x_unit
        self.K.unit = y_unit * x_unit

    def evaluate(self, x, lower_bound, upper_bound, K):
        # This makes the prior proper because it is the integral between lower_bound and upper_bound

        res = np.where((x > lower_bound) & (x < upper_bound), K / x, 0)

        if isinstance(x, astropy_units.Quantity):

            return res * self.y_unit

        else:

            return res

    def from_unit_cube(self, x):
        """
        Used by multinest

        :param x: 0 < x < 1
        :param lower_bound:
        :param upper_bound:
        :return:
        """

        low = math.log10(self.lower_bound.value)
        up = math.log10(self.upper_bound.value)

        spread = up - low
        par = 10 ** (x * spread + low)

        return par


# noinspection PyPep8Naming
class Blackbody(Function1D):
    r"""

    description :
        A blackbody function

    latex : $f(x) = K \frac{x^2}{\exp(\frac{x}{kT}) -1}  $

    parameters :
        K :
            desc :
            initial value : 1e-4
            min : 0.
    
        kT :
            desc : temperature of the blackbody
            initial value : 30.0
            min: 0.
    """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):
        # The normalization has the same units as y
        self.K.unit = y_unit / x_unit ** 2

        # The break point has always the same dimension as the x variable
        self.kT.unit = x_unit

    def evaluate(self, x, K, kT):
        return K * x ** 2 / (np.exp(x / kT) - 1)


# noinspection PyPep8Naming
class Sin(Function1D):
    r"""
    description :

        A sinusodial function

    latex : $ K~\sin{(2\pi f x + \phi)} $

    parameters :

        K :

            desc : Normalization
            initial value : 1

        f :

            desc : frequency
            initial value : 1.0 / (2 * np.pi)
            min : 0

        phi :

            desc : phase
            initial value : 0
            min : -np.pi
            max : +np.pi
            unit: rad

    tests :
        - { x : 0.0, function value: 0.0, tolerance: 1e-10}
        - { x : 1.5707963267948966, function value: 1.0, tolerance: 1e-10}

    """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):
        # The normalization has the same unit of y
        self.K.unit = y_unit

        # The unit of f is 1 / [x] because fx must be a pure number. However,
        # np.pi of course doesn't have units, so we add a rad
        self.f.unit = x_unit ** (-1) * astropy_units.rad

        # The unit of phi is always the same (radians)

        self.phi.unit = astropy_units.rad

    # noinspection PyPep8Naming
    def evaluate(self, x, K, f, phi):
        return K * np.sin(2 * np.pi * f * x + phi)


if has_naima:

    class Synchrotron(Function1D):
        r"""
        description :

            Synchrotron spectrum from an input particle distribution, using Naima (naima.readthedocs.org)

        latex: not available

        parameters :

            B :

                desc : magnetic field
                initial value : 3.24e-6
                unit: Gauss

            distance :

                desc : distance of the source
                initial value : 1.0
                unit : kpc

            emin :

                desc : minimum energy for the particle distribution
                initial value : 1
                fix : yes
                unit: GeV

            emax :
                desc : maximum energy for the particle distribution
                initial value : 510e3
                fix : yes
                unit: GeV

            need:

                desc: number of points per decade in which to evaluate the function
                initial value : 10
                min : 2
                max : 100
                fix : yes

        """

        __metaclass__ = FunctionMeta

        def _set_units(self, x_unit, y_unit):

            # This function can only be used as a spectrum,
            # so let's check that x_unit is a energy and y_unit is
            # differential flux

            if hasattr(x_unit, "physical_type") and x_unit.physical_type == 'energy':

                # Now check that y is a differential flux
                current_units = get_units()
                should_be_unitless = y_unit * (current_units.energy * current_units.time * current_units.area)

                if not hasattr(should_be_unitless, 'physical_type') or \
                                should_be_unitless.decompose().physical_type != 'dimensionless':
                    # y is not a differential flux
                    raise InvalidUsageForFunction("Unit for y is not differential flux. The function synchrotron "
                                                  "can only be used as a spectrum.")
            else:

                raise InvalidUsageForFunction("Unit for x is not an energy. The function synchrotron can only be used "
                                              "as a spectrum")

                # we actually don't need to do anything as the units are already set up

        def set_particle_distribution(self, function):

            self._particle_distribution = function

            # Now set the units for the function

            current_units = get_units()

            self._particle_distribution.set_units(current_units.energy, current_units.energy ** (-1))

            # Naima wants a function which accepts a quantity as x (in units of eV) and returns an astropy quantity,
            # so we need to create a wrapper which will remove the unit from x and add the unit to the return
            # value

            self._particle_distribution_wrapper = lambda x: function(x.value) / current_units.energy

        def get_particle_distribution(self):

            return self._particle_distribution

        particle_distribution = property(get_particle_distribution, set_particle_distribution,
                                         doc="""Get/set particle distribution for electrons""")

        # noinspection PyPep8Naming
        def evaluate(self, x, B, distance, emin, emax, need):

            _synch = naima.models.Synchrotron(self._particle_distribution_wrapper, B * astropy_units.Gauss,
                                              Eemin=emin * astropy_units.GeV,
                                              Eemax=emax * astropy_units.GeV, nEed=need)

            return _synch.flux(x * get_units().energy, distance=distance * astropy_units.kpc).value

        def to_dict(self, minimal=False):

            data = super(Function1D, self).to_dict(minimal)

            if not minimal:
                data['extra_setup'] = {'particle_distribution': self.particle_distribution.path}

            return data


class Line(Function1D):
    r"""
    description :

        A linear function

    latex : $ a * x + b $

    parameters :

        a :

            desc : linear coefficient
            initial value : 1

        b :

            desc : intercept
            initial value : 0

    """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):
        # a has units of y_unit / x_unit, so that a*x has units of y_unit
        self.a.unit = y_unit / x_unit

        # b has units of y
        self.b.unit = y_unit

    def evaluate(self, x, a, b):
        return a * x + b


class Constant(Function1D):
    r"""
        description :

            Return k

        latex : $ k $

        parameters :

            k :

                desc : Constant value
                initial value : 0

        """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):
        self.k.unit = y_unit

    def evaluate(self, x, k):
        return k


class Band(Function1D):
    r"""
    description :

        Band model from Band et al., 1993, parametrized with the peak energy

    latex : $  $

    parameters :

        K :

            desc : Differential flux at the pivot energy
            initial value : 1e-4

        alpha :

            desc : low-energy photon index
            initial value : -1.0
            min : -1.5
            max : 3

        xp :

            desc : peak in the x * x * N (nuFnu if x is a energy)
            initial value : 500
            min : 10

        beta :

            desc : high-energy photon index
            initial value : -2.0
            min : -5.0
            max : -1.6

        piv :

            desc : pivot energy
            initial value : 100.0
            fix : yes
    """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):
        # The normalization has the same units as y
        self.K.unit = y_unit

        # The break point has always the same dimension as the x variable
        self.xp.unit = x_unit

        self.piv.unit = x_unit

        # alpha and beta are dimensionless
        self.alpha.unit = astropy_units.dimensionless_unscaled
        self.beta.unit = astropy_units.dimensionless_unscaled

    def evaluate(self, x, K, alpha, xp, beta, piv):
        E0 = xp / (2 + alpha)

        if (alpha < beta):
            raise ModelAssertionViolation("Alpha cannot be less than beta")

        idx = x < (alpha - beta) * E0

        # The K * 0 part is a trick so that out will have the right units (if the input
        # has units)

        out = np.zeros(x.shape) * K * 0

        out[idx] = K * np.power(x[idx] / piv, alpha) * np.exp(-x[idx] / E0)
        out[~idx] = K * np.power((alpha - beta) * E0 / piv, alpha - beta) * np.exp(beta - alpha) * \
                    np.power(x[~idx] / piv, beta)

        return out


class Band_Calderone(Function1D):
    r"""
    description :

        The Band model from Band et al. 1993, implemented however in a way which reduces the covariances between
        the parameters (Calderone et al., MNRAS, 448, 403C, 2015)

    latex : $ \text{(Calderone et al., MNRAS, 448, 403C, 2015)} $

    parameters :

        alpha :
            desc : The index for x smaller than the x peak
            initial value : -1
            min : -10
            max : 10

        beta :

            desc : index for x greater than the x peak (only if opt=1, i.e., for the
                   Band model)
            initial value : -2.2
            min : -7
            max : -1

        xp :

            desc : position of the peak in the x*x*f(x) space (if x is energy, this is the nuFnu or SED space)
            initial value : 200.0
            min : 0

        F :

            desc : integral in the band defined by a and b
            initial value : 1e-6

        a:

            desc : lower limit of the band in which the integral will be computed
            initial value : 1.0
            min : 0
            fix : yes

        b:

            desc : upper limit of the band in which the integral will be computed
            initial value : 10000.0
            min : 0
            fix : yes

        opt :

            desc : option to select the spectral model (0 corresponds to a cutoff power law, 1 to the Band model)
            initial value : 1
            min : 0
            max : 1
            fix : yes

    """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):

        # alpha and beta are always unitless

        self.alpha.unit = astropy_units.dimensionless_unscaled
        self.beta.unit = astropy_units.dimensionless_unscaled

        # xp has the same dimension as x
        self.xp.unit = x_unit

        # F is the integral over x, so it has dimensions y_unit * x_unit
        self.F.unit = y_unit * x_unit

        # a and b have the same units of x
        self.a.unit = x_unit
        self.b.unit = x_unit

        # opt is just a flag, and has no units
        self.opt.unit = astropy_units.dimensionless_unscaled

    @staticmethod
    def ggrb_int_cpl(a, Ec, Emin, Emax):

        # Gammaincc does not support quantities
        i1 = gammaincc(2 + a, Emin / Ec) * gamma(2 + a)
        i2 = gammaincc(2 + a, Emax / Ec) * gamma(2 + a)

        return -Ec * Ec * (i2 - i1)

    @staticmethod
    def ggrb_int_pl(a, b, Ec, Emin, Emax):

        pre = pow(a - b, a - b) * math.exp(b - a) / pow(Ec, b)

        if b != -2:

            return pre / (2 + b) * (pow(Emax, 2 + b) - pow(Emin, 2 + b))

        else:

            return pre * math.log(Emax / Emin)

    def evaluate(self, x, alpha, beta, xp, F, a, b, opt):

        assert opt == 0 or opt == 1, "Opt must be either 0 or 1"

        if alpha < beta:
            raise ModelAssertionViolation("Alpha cannot be smaller than beta")

        if alpha < -2:
            raise ModelAssertionViolation("Alpha cannot be smaller than -2")

        # Cutoff energy

        if alpha == -2:

            Ec = xp / 0.0001  # TRICK: avoid a=-2

        else:

            Ec = xp / (2 + alpha)

        # Split energy

        Esplit = (alpha - beta) * Ec

        # Evaluate model integrated flux and normalization

        if isinstance(alpha, astropy_units.Quantity):

            # The following functions do not allow the use of units
            alpha_ = alpha.value
            Ec_ = Ec.value
            a_ = a.value
            b_ = b.value
            Esplit_ = Esplit.value
            beta_ = beta.value

            unit_ = self.x_unit

        else:

            alpha_, Ec_, a_, b_, Esplit_, beta_ = alpha, Ec, a, b, Esplit, beta
            unit_ = 1.0

        if opt == 0:

            # Cutoff power law

            intflux = self.ggrb_int_cpl(alpha_, Ec_, a_, b_)

        else:

            # Band model

            if a <= Esplit and Esplit <= b:

                intflux = (self.ggrb_int_cpl(alpha_, Ec_, a_, Esplit_) +
                           self.ggrb_int_pl(alpha_, beta_, Ec_, Esplit_, b_))

            else:

                if Esplit < a:

                    intflux = self.ggrb_int_pl(alpha_, beta_, Ec_, a_, b_)

                else:

                    raise RuntimeError("Esplit > emax!")

        erg2keV = 6.24151e8

        norm = F * erg2keV / (intflux * unit_)

        if opt == 0:

            # Cutoff power law

            flux = np.power(x / Ec, alpha) * np.exp(- x / Ec)

        else:

            # The norm * 0 is to keep the units right

            flux = np.zeros(x.shape) * norm * 0

            idx = x < Esplit

            flux[idx] = norm * np.power(x[idx] / Ec, alpha) * np.exp(-x[idx] / Ec)
            flux[~idx] = norm * pow(alpha - beta, alpha - beta) * math.exp(beta - alpha) * np.power(x[~idx] / Ec, beta)

        return flux


class Log_parabola(Function1D):
    r"""
    description :

        A log-parabolic function

    latex : $ K \left( \frac{x}{piv} \right)^{\alpha +\beta \log{\left( \frac{x}{piv} \right)}} $

    parameters :

        K :

            desc : Normalization
            initial value : 1.0

        piv :
            desc : Pivot (keep this fixed)
            initial value : 1
            fix : yes

        alpha :

            desc : index
            initial value : -2.0

        beta :

            desc : curvature (negative is concave, positive is convex)
            initial value : -1.0

    """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):

        # K has units of y

        self.K.unit = y_unit

        # piv has the same dimension as x
        self.piv.unit = x_unit

        # alpha and beta are dimensionless
        self.alpha.unit = astropy_units.dimensionless_unscaled
        self.beta.unit = astropy_units.dimensionless_unscaled

    def evaluate(self, x, K, piv, alpha, beta):

        xx = np.divide(x, piv)

        try:

            return K * xx ** (alpha + beta * np.log10(xx))

        except ValueError:

            # The current version of astropy (1.1.x) has a bug for which quantities that have become
            # dimensionless because of a division (like xx here) are not recognized as such by the power
            # operator, which throws an exception: ValueError: Quantities and Units may only be raised to a scalar power
            # This is a quick fix, waiting for astropy 1.2 which will fix this

            xx = xx.to('')

            return K * xx ** (alpha + beta * np.log10(xx))

    @property
    def peak_energy(self):
        """
        Returns the peak energy in the nuFnu spectrum

        :return: peak energy in keV
        """

        # Eq. 6 in Massaro et al. 2004
        # (http://adsabs.harvard.edu/abs/2004A%26A...413..489M)

        return self.piv.value * pow(10, (2 + self.alpha.value) / (2 * self.beta.value))


if has_gsl:
    class Cutoff_powerlaw_flux(Function1D):
        r"""
            description :

                A cutoff power law having the flux as normalization, which should reduce the correlation among
                parameters.

            latex : $ \frac{F}{T(b)-T(a)} ~x^{index}~\exp{(-x/x_{c})}~\text{with}~T(x)=-x_{c}^{index+1} \Gamma(index+1, x/C)~\text{(}\Gamma\text{ is the incomplete gamma function)} $

            parameters :

                F :

                    desc : Integral between a and b
                    initial value : 1e-5

                index :

                    desc : photon index
                    initial value : -2.0

                xc :

                    desc : cutoff position
                    initial value : 50.0

                a :

                    desc : lower bound for the band in which computing the integral F
                    initial value : 1.0
                    fix : yes

                b :

                    desc : upper bound for the band in which computing the integral F
                    initial value : 100.0
                    fix : yes
            """

        __metaclass__ = FunctionMeta

        def _set_units(self, x_unit, y_unit):
            # K has units of y * x
            self.F.unit = y_unit * x_unit

            # alpha is dimensionless
            self.index.unit = astropy_units.dimensionless_unscaled

            # xc, a and b have the same dimension as x
            self.xc.unit = x_unit
            self.a.unit = x_unit
            self.b.unit = x_unit

        @staticmethod
        def _integral(a, b, index, ec):
            ap1 = index + 1

            integrand = lambda x: -pow(ec, ap1) * gamma_inc(ap1, x / ec)

            return integrand(b) - integrand(a)

        def evaluate(self, x, F, index, xc, a, b):
            this_integral = self._integral(a, b, index, xc)

            return F / this_integral * np.power(x, index) * np.exp(-1 * np.divide(x, xc))


class Exponential_cutoff(Function1D):
    r"""
        description :

            An exponential cutoff

        latex : $ K \exp{(-x/xc)} $

        parameters :

            K :

                desc : Normalization
                initial value : 1.0
                fix : no

            xc :
                desc : cutoff
                initial value : 100
                min : 1
        """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):
        # K has units of y

        self.K.unit = y_unit

        # piv has the same dimension as x
        self.xc.unit = x_unit

    def evaluate(self, x, K, xc):
        return K * np.exp(np.divide(x, -xc))

class DMFitFunction(Function1D):
    r"""
        description :
        
            Class that evaluates the spectrum for a DM particle of a given
            mass, channel, cross section, and J-factor. Based on standard
            Fermi Science Tools function DMFitFunction. Note input table only
            calculated spectra up to m_DM of 10 TeV
            
            The parameterization is given by
            
            F(x) = 1 / (8 * pi) * (1/mass^2) * sigmav * J * dN/dE(E,mass,i)
            
            Note that this class assumes that mass and J-factor are provided
            in units of GeV and GeV^2 cm^-5
            
        latex : $$
        
        parameters :
        
            mass :
                desc : DM mass (GeV)
                initial value : 10
                fix : yes
                
            channel :
                desc : DM annihilation channel
                initial value : 4
                fix : yes
            
            sigmav : 
                desc : DM annihilation cross section (cm^3/s)
                initial value : 1.e-26
            
            J :
                desc : Target total J-factor (GeV^2 cm^-5)
                initial value : 1.e20
                fix : yes
        """
    
    __metaclass__ = FunctionMeta
    
    def _setup(self):
        
        astroDir = astromodels.__file__
        astroDir = astroDir.split('__init__.py')[0]
        tablepath = astroDir+'functions/gammamc_dif.dat'
        self._data = np.loadtxt(tablepath)
        
        """
            Mapping between the channel codes and the rows in the gammamc file
            
            1 : 8, # ee
            2 : 6, # mumu
            3 : 3, # tautau
            4 : 1, # bb
            5 : 2, # tt
            6 : 7, # gg
            7 : 4, # ww
            8 : 5, # zz
            9 : 0, # cc
            10 : 10, # uu
            11 : 11, # dd
            12 : 9, # ss
        """
        
        channel_index_mapping = {
            1 : 8, # ee
            2 : 6, # mumu
            3 : 3, # tautau
            4 : 1, # bb
            5 : 2, # tt
            6 : 7, # gg
            7 : 4, # ww
            8 : 5, # zz
            9 : 0, # cc
            10 : 10, # uu
            11 : 11, # dd
            12 : 9, # ss
        }
        
        # Number of decades in x = log10(E/M)
        ndec = 10.0
        xedge = np.linspace(0,1.0,251)
        self._x = 0.5*(xedge[1:]+xedge[:-1])*ndec - ndec

        ichan = channel_index_mapping[int(self.channel.value)]

        # These are the mass points
        self._mass = np.array([2.0,4.0,6.0,8.0,10.0,
                       25.0,50.0,80.3,91.2,100.0,
                       150.0,176.0,200.0,250.0,350.0,500.0,750.0,
                       1000.0,1500.0,2000.0,3000.0,5000.0,7000.0,1E4])
        self._dn = self._data.reshape((12,24,250))
            
        self._dn_interp = RegularGridInterpolator([self._mass,self._x],
                                                    self._dn[ichan,:,:],
                                                    bounds_error=False,
                                                    fill_value=None)

        if self.mass.value > 10000:
            print "Warning: DMFitFunction only appropriate for masses <= 10 TeV"
            print "To model DM from 2 GeV < mass < 1 PeV use DMSpectra"

    def _set_units(self, x_unit, y_unit):
        
        self.mass.unit = u.GeV
        self.channel.unit = astropy_units.dimensionless_unscaled
        self.sigmav.unit = u.cm**3 / u.s
        self.J.unit = u.GeV**2 / u.cm**5
    
    def print_channel_mapping(self):
    
        channel_mapping = {
        1 : 'ee',
        2 : 'mumu',
        3 : 'tautau',
        4 : 'bb',
        5 : 'tt',
        6 : 'gg',
        7 : 'ww',
        8 : 'zz',
        9 : 'cc',
        10 : 'uu',
        11 : 'dd',
        12 : 'ss',
        }
    
        print channel_mapping
    
        return channel_mapping
    
    # noinspection PyPep8Naming
    def evaluate(self, x, mass,channel,sigmav,J):
        
        keVtoMeV = 1./1000.
        xx = np.multiply(x,keVtoMeV) # xm expects gamma ray energies in MeV
        
        xm = np.log10(np.divide(xx,mass)) - 3.0
        phip = 1./(8.*np.pi)*np.power(mass,-2)*(sigmav*J) # units of this should be 1 / cm**2 / s
        dn = self._dn_interp((mass,xm))
        dn[xm > 0] = 0
        
        return np.multiply(phip,np.divide(dn,x))

class DMSpectra(Function1D):
    r"""
        description :
        
            Class that evaluates the spectrum for a DM particle of a given
            mass, channel, cross section, and J-factor. Combines Pythia-based tables
            from both Fermi (2 GeV < m_DM < 10 TeV) and HAWC (10 TeV < m_dm < 1 PeV)
            
            The parameterization is given by
            
            F(x) = 1 / (8 * pi) * (1/mass^2) * sigmav * J * dN/dE(E,mass,i)
            
            Note that this class assumes that mass and J-factor are provided
            in units of GeV and GeV^2 cm^-5
        
        latex : $$
        
        parameters :
        
            mass :
                desc : DM mass (GeV)
                initial value : 10
                fix : yes
        
            channel :
                desc : DM annihilation channel
                initial value : 4
                fix : yes
            
            sigmav :
                desc : DM annihilation cross section (cm^3/s)
                initial value : 1.e-26
            
            J :
                desc : Target total J-factor (GeV^2 cm^-5)
                initial value : 1.e20
                fix : yes
        """
    
    __metaclass__ = FunctionMeta
    
    def _setup(self):
        
        astroDir = astromodels.__file__
        astroDir = astroDir.split('__init__.py')[0]
        tablepath_h = astroDir+'functions/dmSpecTab.npy'
        self._data_h = np.load(tablepath_h)
        tablepath_f = astroDir+'functions/gammamc_dif.dat'
        self._data_f = np.loadtxt(tablepath_f)
        
        """
            Mapping between the channel codes and the rows in the gammamc file
            dmSpecTab.npy created to match this mapping too
            
            1 : 8, # ee
            2 : 6, # mumu
            3 : 3, # tautau
            4 : 1, # bb
            5 : 2, # tt
            6 : 7, # gg
            7 : 4, # ww
            8 : 5, # zz
            9 : 0, # cc
            10 : 10, # uu
            11 : 11, # dd
            12 : 9, # ss
            """
        
        channel_index_mapping = {
            1 : 8, # ee
            2 : 6, # mumu
            3 : 3, # tautau
            4 : 1, # bb
            5 : 2, # tt
            6 : 7, # gg
            7 : 4, # ww
            8 : 5, # zz
            9 : 0, # cc
            10 : 10, # uu
            11 : 11, # dd
            12 : 9, # ss
        }
        
        # Number of decades in x = log10(E/M)
        ndec = 10.0
        xedge = np.linspace(0,1.0,251)
        self._x = 0.5*(xedge[1:]+xedge[:-1])*ndec - ndec
        
        ichan = channel_index_mapping[int(self.channel.value)]
        
        # These are the mass points in GeV
        self._mass_h = np.array([50.,61.2,74.91,91.69,112.22,137.36,168.12,205.78,251.87,308.29,
                               377.34,461.86,565.31,691.93,846.91,1036.6,1268.78,1552.97,1900.82,
                               2326.57,2847.69,3485.53,4266.23,5221.81,6391.41,7823.0,9575.23,
                               11719.94,14345.03,17558.1,21490.85,26304.48,32196.3,39407.79,48234.54,
                               59038.36,72262.07,88447.7,108258.66,132506.99,162186.57,198513.95,
                               242978.11,297401.58,364015.09,445549.04,545345.37,667494.6,817003.43,1000000.])
            
       
        # These are the mass points in GeV
        self._mass_f = np.array([2.0,4.0,6.0,8.0,10.0,
                              25.0,50.0,80.3,91.2,100.0,
                              150.0,176.0,200.0,250.0,350.0,500.0,750.0,
                              1000.0,1500.0,2000.0,3000.0,5000.0,7000.0,1E4])
                              
        self._mass = np.append(self._mass_f,self._mass_h[27:])
        
        self._dn_f = self._data_f.reshape((12,24,250))
        self._dn_h = self._data_h
        
        self._dn = np.zeros((12,len(self._mass),250))
        self._dn[:,0:24,:] = self._dn_f
        self._dn[:,24:,:] = self._dn_h[:,27:,:]
        
        self._dn_interp = RegularGridInterpolator([self._mass,self._x],
                                                   self._dn[ichan,:,:],
                                                   bounds_error=False,
                                                   fill_value=None)
    
        if self.channel.value in [1,6,7] and self.mass.value > 10000.:
            print "ERROR: currently spectra for selected channel and mass not implemented."
            print "Spectra for channels ['ee','gg','WW'] currently not available for mass > 10 TeV"
    

    def _set_units(self, x_unit, y_unit):
    
        self.mass.unit = u.GeV
        self.channel.unit = astropy_units.dimensionless_unscaled
        self.sigmav.unit = u.cm**3 / u.s
        self.J.unit = u.GeV**2 / u.cm**5
    
    def print_channel_mapping(self):
        
        channel_mapping = {
        1 : 'ee',
        2 : 'mumu',
        3 : 'tautau',
        4 : 'bb',
        5 : 'tt',
        6 : 'gg',
        7 : 'ww',
        8 : 'zz',
        9 : 'cc',
        10 : 'uu',
        11 : 'dd',
        12 : 'ss',
        }
        
        print channel_mapping
        
        return channel_mapping
    
    # noinspection PyPep8Naming
    def evaluate(self, x, mass,channel,sigmav,J):
        
        keVtoMeV = 1./1000.
        xx = np.multiply(x,keVtoMeV) # xm expects gamma ray energies in MeV
        
        xm = np.log10(np.divide(xx,mass)) - 3.0
        phip = 1./(8.*np.pi)*np.power(mass,-2)*(sigmav*J) # units of this should be 1 / cm**2
        dn = self._dn_interp((mass,xm)) # note this is unitless (dx = d(xm))
        dn[xm > 0] = 0
        
        return np.multiply(phip,np.divide(dn,x))
