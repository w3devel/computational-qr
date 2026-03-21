/// Complex number arithmetic (no external crate needed).

#[derive(Clone, Copy, Debug)]
pub struct C {
    pub re: f64,
    pub im: f64,
}

impl C {
    #[inline]
    pub fn new(re: f64, im: f64) -> Self {
        Self { re, im }
    }

    #[inline]
    pub fn zero() -> Self {
        Self::new(0.0, 0.0)
    }

    #[inline]
    pub fn mul(self, rhs: Self) -> Self {
        Self::new(
            self.re * rhs.re - self.im * rhs.im,
            self.re * rhs.im + self.im * rhs.re,
        )
    }

    #[inline]
    pub fn add(self, rhs: Self) -> Self {
        Self::new(self.re + rhs.re, self.im + rhs.im)
    }

    #[inline]
    pub fn norm_sq(self) -> f64 {
        self.re * self.re + self.im * self.im
    }
}

/// A dense square complex matrix of size `dim × dim`.
///
/// Entries are stored in row-major order.
#[derive(Clone)]
pub struct Matrix {
    pub dim: usize,
    pub data: Vec<C>,
}

impl Matrix {
    pub fn new(dim: usize) -> Self {
        Self {
            dim,
            data: vec![C::zero(); dim * dim],
        }
    }

    #[inline]
    pub fn get(&self, row: usize, col: usize) -> C {
        self.data[row * self.dim + col]
    }

    #[inline]
    pub fn set(&mut self, row: usize, col: usize, val: C) {
        self.data[row * self.dim + col] = val;
    }

    /// Matrix-vector product `Av`, in-place result into `out`.
    pub fn apply(&self, v: &[C], out: &mut [C]) {
        let d = self.dim;
        for i in 0..d {
            let mut acc = C::zero();
            for j in 0..d {
                acc = acc.add(self.get(i, j).mul(v[j]));
            }
            out[i] = acc;
        }
    }
}

// ---- Standard gate matrices ------------------------------------------------

const INV_SQRT2: f64 = std::f64::consts::FRAC_1_SQRT_2;
const PI: f64 = std::f64::consts::PI;

fn c(re: f64, im: f64) -> C {
    C::new(re, im)
}

/// Build a gate matrix from a flat list of (re, im) pairs (row-major).
fn mat2(entries: &[(f64, f64)]) -> Matrix {
    let dim = (entries.len() as f64).sqrt() as usize;
    let mut m = Matrix::new(dim);
    for (k, &(re, im)) in entries.iter().enumerate() {
        m.data[k] = c(re, im);
    }
    m
}

pub fn gate_i() -> Matrix {
    mat2(&[(1., 0.), (0., 0.), (0., 0.), (1., 0.)])
}

pub fn gate_x() -> Matrix {
    mat2(&[(0., 0.), (1., 0.), (1., 0.), (0., 0.)])
}

pub fn gate_y() -> Matrix {
    mat2(&[(0., 0.), (0., -1.), (0., 1.), (0., 0.)])
}

pub fn gate_z() -> Matrix {
    mat2(&[(1., 0.), (0., 0.), (0., 0.), (-1., 0.)])
}

pub fn gate_h() -> Matrix {
    mat2(&[
        (INV_SQRT2, 0.), (INV_SQRT2, 0.),
        (INV_SQRT2, 0.), (-INV_SQRT2, 0.),
    ])
}

pub fn gate_s() -> Matrix {
    mat2(&[(1., 0.), (0., 0.), (0., 0.), (0., 1.)])
}

pub fn gate_t() -> Matrix {
    let (re, im) = ((PI / 4.0).cos(), (PI / 4.0).sin());
    mat2(&[(1., 0.), (0., 0.), (0., 0.), (re, im)])
}

pub fn gate_cnot() -> Matrix {
    // 4×4 in big-endian basis:
    // |00⟩→|00⟩, |01⟩→|01⟩, |10⟩→|11⟩, |11⟩→|10⟩
    let e = &[
        (1., 0.), (0., 0.), (0., 0.), (0., 0.),
        (0., 0.), (1., 0.), (0., 0.), (0., 0.),
        (0., 0.), (0., 0.), (0., 0.), (1., 0.),
        (0., 0.), (0., 0.), (1., 0.), (0., 0.),
    ];
    mat2(e)
}

pub fn gate_swap() -> Matrix {
    let e = &[
        (1., 0.), (0., 0.), (0., 0.), (0., 0.),
        (0., 0.), (0., 0.), (1., 0.), (0., 0.),
        (0., 0.), (1., 0.), (0., 0.), (0., 0.),
        (0., 0.), (0., 0.), (0., 0.), (1., 0.),
    ];
    mat2(e)
}

/// Look up a standard gate by name; returns None for unknown names.
pub fn standard_gate(name: &str) -> Option<Matrix> {
    match name {
        "I"    => Some(gate_i()),
        "X"    => Some(gate_x()),
        "Y"    => Some(gate_y()),
        "Z"    => Some(gate_z()),
        "H"    => Some(gate_h()),
        "S"    => Some(gate_s()),
        "T"    => Some(gate_t()),
        "CNOT" => Some(gate_cnot()),
        "SWAP" => Some(gate_swap()),
        _      => None,
    }
}

/// Build a matrix from user-supplied [re, im] data.
pub fn custom_gate(dim: usize, data: &[[f64; 2]]) -> Result<Matrix, String> {
    if dim == 0 || (dim & (dim - 1)) != 0 {
        return Err(format!("Custom gate dim must be a power of 2, got {dim}"));
    }
    if data.len() != dim * dim {
        return Err(format!(
            "Custom gate data length {} != dim*dim = {}",
            data.len(),
            dim * dim
        ));
    }
    let mut m = Matrix::new(dim);
    for (k, &[re, im]) in data.iter().enumerate() {
        m.data[k] = c(re, im);
    }
    Ok(m)
}
