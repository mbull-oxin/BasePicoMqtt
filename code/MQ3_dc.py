from machine import Timer
import MQ_base_dc

A=[2.71494E+02, -3.10999E+02, 6.85051E+02, -3.47587E+02, 7.47499E+01]

class DC(MQ_base_dc.DC):
    def convert(self,raw_v):
        B=[raw_v*raw_v]
        for ind in range(3):
            B.append(B[ind]*raw_v)
        return ('ethanol',A[0]*raw_v+A[1]*B[0]+A[2]*B[1]+A[3]*B[2]+A[4]*B[3],'ppm')
