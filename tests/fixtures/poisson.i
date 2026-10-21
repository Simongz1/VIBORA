[Mesh]
 type = GeneratedMesh
 dim = 1
 nx = 4
[]
[Variables]
 [u]
 []
[]
[Kernels]
 [diff]
  type = Diffusion
  variable = u
 []
 [source]
  type = ViboraFixtureSource
  variable = u
  source = 1
 []
[]
[BCs]
 [zero]
  type = DirichletBC
  variable = u
  boundary = 'left right'
  value = 0
 []
[]
[Postprocessors]
 [midpoint]
  type = PointValue
  variable = u
  point = '0.5 0 0'
 []
[]
[Executioner]
 type = Steady
 solve_type = NEWTON
 petsc_options_iname = '-pc_type'
 petsc_options_value = 'lu'
[]
[Outputs]
 csv = true
[]
