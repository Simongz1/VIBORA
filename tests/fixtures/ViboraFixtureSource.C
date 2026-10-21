#include "ViboraFixtureSource.h"
registerMooseObject("ViboraPhysicsApp", ViboraFixtureSource);
InputParameters ViboraFixtureSource::validParams() {
 auto p=Kernel::validParams();
 p.addRequiredParam<Real>("source","Constant source for the build regression fixture");
 return p;
}
ViboraFixtureSource::ViboraFixtureSource(const InputParameters & p)
 : Kernel(p), _source(getParam<Real>("source")) {}
Real ViboraFixtureSource::computeQpResidual() { return -_test[_i][_qp]*_source; }
