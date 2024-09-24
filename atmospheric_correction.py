import numpy as np
import xarray
from pyeosim.datasets import _dload


class _SREM_atmospheric_correction(object):
    """
    Implements the Simplified Robust Estimation Method
    
    Methods
    -------
    transform(signal)
        converts at-sensor radiance to estimated BOA reflectance
    """
    def __init__(self, solar_z, solar_a, view_z, view_a,
                 day_of_year, spectral_response, solar_spectrum='E490'):
        """
        Parameters
        ----------
        solar_z : float
            solar zenith in deg
        solar_a : float
            solar angle in deg
        view_z : float
            view zenith in deg
        view_a : float
            view angle in deg
        day_of_year : int
            day of Julian calendar
        spectral_response : SRF
            spectral response object from pyeosim.spectral
        solar_spectrum : str or xarray.DataArray, optional
            path to E490 solar extraterrestrial spectrum (default) or
            DataArray with irradiance in W m-2 nm-1 and wavelength
            in nm
        """
        self.solar_z = solar_z
        self.solar_a = solar_a
        self.view_z = view_z
        self.view_a = view_a
        self.doy = day_of_year
        self.spectral_response = spectral_response
        # either load or use directly
        if solar_spectrum == 'E490':
            self.solar_spectrum = self._load_solar_E()
        else:
            self.solar_spectrum = solar_spectrum
        self._generate_params()
        
    def _nm_to_um(self, x):
        return x / 1e3

    def _load_solar_E(self):
        # This is a standard Solar Extraterrestrial Spectrum at 1 AU
        return _dload('SOLAR_SPECTRUM_ASTME490').sel(wavelength=slice(300,1000))
        
    def _rho_s(self, rho_toa, rho_r, S_atm, T_s, T_v):
        return (rho_toa - rho_r) / (S_atm * (rho_toa - rho_r) + (T_s * T_v))

    def _mu_s(self, solar_z):
        return np.cos(np.deg2rad(solar_z))

    def _mu_v(self, view_z):
        return np.cos(np.deg2rad(view_z))

    def _d(self, day_of_year):
        # solar distance in AUs
        # ellipticity coefficients
        C0 = 0.03275104
        C1 = 59.66638337
        C2 = 0.96804905
        return C0 * np.cos(day_of_year / C1) + C2
    
    def _E_sun(self, spectral_response, solar_spectrum):
        return spectral_response.transform(solar_spectrum)
    
    def _rho_toa(self, L, d, mu_s, E_sun):
        # generate per- band E_sun
        return (np.pi * L * d**2) / (E_sun * mu_s)

    def _rho_r(self, P_r, M, mu_s, mu_v, tau_r):
        return P_r * ((1-np.exp(-M * tau_r)) / (4 * (mu_s + mu_v)))

    def _M(self, mu_s, mu_v):
        return (1/mu_s) + (1/mu_v)

    def _tau_r(self, spectral_response):
        # Original paper is Hansen and Travis, 1974
        # https://pubs.giss.nasa.gov/docs/1974/1974_Hansen_ha09500o.pdf
        C0 = 0.008569
        C1 = 0.0113
        # C2 = 0.0013 # incorrect value in SREM paper
        C2 = 0.00013 # correct value from original paper
        tau_r = []
        for wlen in spectral_response.band_wavelengths.values():
            # C coefficients derived for wavelength in microns
            # convert nm to um
            lam = self._nm_to_um(wlen)
            tau_r.append(C0 * (lam ** -4) * (1 + (C1 * (lam ** -2)) + (C2 * (lam ** -4))))
        return xarray.DataArray(tau_r, coords={'band':np.arange(len(tau_r))})

    def _P_r(self, Theta):
        A = 0.9587256
        B = 1 - A
        return ((3 * A) / 4 + B) * (1+(np.cos(np.deg2rad(Theta)) **2))

    def _S_atm(self, tau_r):
        return (0.92 * tau_r) * np.exp(-tau_r)

    def _T_s(self, mu_s, tau_r):
        return np.exp((-tau_r) / mu_s) + (np.exp((-tau_r) / mu_s) * (np.exp((0.52 * tau_r) / mu_s) -1))

    def _T_v(self, mu_v, tau_r):
        return np.exp((-tau_r) / mu_v) + (np.exp((-tau_r) / mu_v) * (np.exp((0.52 * tau_r) / mu_v) -1))
    
    def _scattering_angle(self, solar_a, view_a, mu_s, mu_v):
        # Defined in 6SV and also in Liu and Liu 2009
        # https://www.researchgate.net/publication/228707385_Aerosol_Optical_Depth_Retrieval_for_Spot_HRV_Images
        phi = np.abs(view_a - solar_a)
        phi_rad = np.deg2rad(phi)
        if phi_rad < 0:
            phi_rad = phi_rad + (2 * np.pi)
        elif phi_rad > (2 * np.pi):
            phi_rad = phi_rad - (2 * np.pi)
        mu_p = np.cos(phi_rad)
        mu_d = -mu_s * mu_v - np.sqrt(1 - mu_s**2) * np.sqrt(1 - mu_v **2) * mu_p
        theta_dif = np.rad2deg(np.arccos(mu_d))
        return theta_dif

    def _generate_params(self):

        self.mu_s = self._mu_s(self.solar_z)
        self.mu_v = self._mu_v(self.view_z)
        self.scattering_angle = self._scattering_angle(self.solar_z, self.view_z, self.mu_s, self.mu_v)
        self.d = self._d(self.doy)
        self.M = self._M(self.mu_s, self.mu_v)
        self.tau_r = self._tau_r(self.spectral_response)
        self.P_r = self._P_r(self.scattering_angle)
        self.E_sun = self._E_sun(self.spectral_response, self.solar_spectrum)
        self.S_atm = self._S_atm(self.tau_r)
        self.T_s = self._T_s(self.mu_s, self.tau_r)
        self.T_v = self._T_v(self.mu_v, self.tau_r)
        self.rho_r = self._rho_r(self.P_r, self.M, self.mu_s, self.mu_v, self.tau_r)
        
    def transform_refl_to_rad(self, rho):
        return ((self.E_sun * self.mu_s * rho) / (self.d ** 2)) / np.pi
    
    def transform(self, x, reflectance=False):
        if reflectance is False:
            self.rho_toa = self._rho_toa(x, self.d, self.mu_s, self.E_sun)
        else:
            self.rho_toa = x
        return self._rho_s(self.rho_toa.copy(), self.rho_r, self.S_atm, self.T_s, self.T_v)

    
class SREM_Reflectance(_SREM_atmospheric_correction):
    """
    Implements the Simplified Robust Estimation Method for top-of-atmosphere reflectance
    """
    def transform(self, x):
        return super().transform(x, True)


class SREM_Radiance(_SREM_atmospheric_correction):
    """
    Implements the Simplified Robust Estimation Method for top-of-atmosphere radiance
    """
    def transform(self, x):
        return super().transform(x, False)
