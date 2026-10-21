#pragma once
#include "Kernel.h"
class ViboraFixtureSource : public Kernel {
public:
 static InputParameters validParams();
 ViboraFixtureSource(const InputParameters & p);
protected:
 Real computeQpResidual() override;
 Real computeQpJacobian() override { return 0; }
 const Real _source;
};
