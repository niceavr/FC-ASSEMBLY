#include<stdio.h>
int main()
{
	 int cmr,pmr,nu;
	 float rate,bill;
	 printf("Enter cmr and pmr values\n");
	 scanf("%d%d",&cmr,&pmr);
	 nu=cmr-pmr;
	 if(nu>=0&&nu<=49)
	    rate=2.75;
	else
	   if(nu>=50 && nu<=99)
	       rate=3.75;
	   else
	     if(nu>=100 && nu<=149)
	         rate=4.75;
	     else
	        if(nu>=150 && nu<=199)
	             rate=5.75;
	        else
	            rate=6.75;
	bill=nu*rate;
	printf("\nnu=%d , Rate = %.2f , Bill amount=%.2f",nu,rate,bill);
	       
}
