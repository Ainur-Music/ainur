"""
Adapted from https://github.com/gudgud96/frechet-audio-distance
"""
import os
import numpy as np
import torch
from torch import nn
from scipy import linalg
from tqdm import tqdm
import soundfile as sf
import resampy

SAMPLE_RATE = 16000

class FAD:
    def __init__(self, use_pca=False, use_activation=False, background=None, verbose=False):
        self.__get_model(use_pca=use_pca, use_activation=use_activation)
        self.background = background
        self.verbose = verbose
    
    def __get_model(self, use_pca=False, use_activation=False):
        """
        Params:
        -- x   : Either 
            (i) a string which is the directory of a set of audio files, or
            (ii) a np.ndarray of shape (num_samples, sample_length)
        """
        self.model = torch.hub.load('harritaylor/torchvggish', 'vggish')
        if not use_pca:
            self.model.postprocess = False
        if not use_activation:
            self.model.embeddings = nn.Sequential(*list(self.model.embeddings.children())[:-1])
        self.model.eval()
    
    def get_embeddings(self, x, sr=SAMPLE_RATE):
        """
        Get embeddings using VGGish model.
        Params:
        -- x    : Either 
            (i) a string which is the directory of a set of audio files, or
            (ii) a list of np.ndarray audio samples
        -- sr   : Sampling rate, if x is a list of audio samples. Default value is 16000.
        """
        embd_lst = []
        for audio in tqdm(x, disable=(not self.verbose)):
            embd = self.model.forward(audio, sr)
            embd = embd.detach().numpy()
            embd_lst.append(embd)
        return np.concatenate(embd_lst, axis=0)
    
    def calculate_embd_statistics(self, embd_lst):
        if isinstance(embd_lst, list):
            embd_lst = np.array(embd_lst)
        mu = np.mean(embd_lst, axis=0)
        sigma = np.cov(embd_lst, rowvar=False)
        return mu, sigma
    
    def calculate_frechet_distance(self, mu1, sigma1, mu2, sigma2, eps=1e-6):
        """
        Adapted from: https://github.com/mseitzer/pytorch-fid/blob/master/src/pytorch_fid/fid_score.py
        
        Numpy implementation of the Frechet Distance.
        The Frechet distance between two multivariate Gaussians X_1 ~ N(mu_1, C_1)
        and X_2 ~ N(mu_2, C_2) is
                d^2 = ||mu_1 - mu_2||^2 + Tr(C_1 + C_2 - 2*sqrt(C_1*C_2)).
        Stable version by Dougal J. Sutherland.
        Params:
        -- mu1   : Numpy array containing the activations of a layer of the
                inception net (like returned by the function 'get_predictions')
                for generated samples.
        -- mu2   : The sample mean over activations, precalculated on an
                representative data set.
        -- sigma1: The covariance matrix over activations for generated samples.
        -- sigma2: The covariance matrix over activations, precalculated on an
                representative data set.
        Returns:
        --   : The Frechet Distance.
        """

        mu1 = np.atleast_1d(mu1)
        mu2 = np.atleast_1d(mu2)

        sigma1 = np.atleast_2d(sigma1)
        sigma2 = np.atleast_2d(sigma2)

        assert mu1.shape == mu2.shape, \
            'Training and test mean vectors have different lengths'
        assert sigma1.shape == sigma2.shape, \
            'Training and test covariances have different dimensions'

        diff = mu1 - mu2

        # Product might be almost singular
        covmean, _ = linalg.sqrtm(sigma1.dot(sigma2), disp=False)
        if not np.isfinite(covmean).all():
            msg = ('fid calculation produces singular product; '
                'adding %s to diagonal of cov estimates') % eps
            print(msg)
            offset = np.eye(sigma1.shape[0]) * eps
            covmean = linalg.sqrtm((sigma1 + offset).dot(sigma2 + offset))

        # Numerical error might give slight imaginary component
        if np.iscomplexobj(covmean):
            if not np.allclose(np.diagonal(covmean).imag, 0, atol=1e-3):
                m = np.max(np.abs(covmean.imag))
                raise ValueError('Imaginary component {}'.format(m))
            covmean = covmean.real

        tr_covmean = np.trace(covmean)

        return (diff.dot(diff) + np.trace(sigma1)
                + np.trace(sigma2) - 2 * tr_covmean)
    
    
    def calculate_embd_statistics_background(self, background, save_path=".tmp/"):
        save_path = os.path.join(save_path, "background_statistics.ptc")
        if os.path.exists(save_path):
            return torch.load(save_path)
        
        embds_background = self.get_embeddings([np.mean(resampy.resample(sample.detach().squeeze().numpy(), 48_000, SAMPLE_RATE), axis=0) for sample in background])
        if len(embds_background) == 0:
            print("[Frechet Audio Distance] background set dir is empty, exitting...")
            return -1
        
        background_statistics = self.calculate_embd_statistics(embds_background)
        torch.save(background_statistics, save_path)
        return background_statistics
    

    def score(self, evaluation):
        embds_eval = self.get_embeddings([np.mean(resampy.resample(sample.detach().numpy(), 48_000, SAMPLE_RATE), axis=0) for sample in evaluation])

        if len(embds_eval) == 0:
            print("[Frechet Audio Distance] eval set dir is empty, exitting...")
            return -1
        mu_background, sigma_background = self.calculate_embd_statistics_background(self.background)
        mu_eval, sigma_eval = self.calculate_embd_statistics(embds_eval)

        fad_score = self.calculate_frechet_distance(
            mu_background, 
            sigma_background, 
            mu_eval, 
            sigma_eval
        )

        return fad_score
    


if __name__ == "__main__":
    background = torch.randn(2**18).numpy()
    eval = torch.randn(2**18).numpy()

    frechet = FAD(
        use_pca=False, 
        use_activation=False,
        background=background,
        verbose=False)

    print(frechet.score(eval))